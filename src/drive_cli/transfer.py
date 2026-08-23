"""Ownership transfer across a Drive folder tree.

Ownership does not cascade in Drive and the flags that move it live on a direct
per-file permission, so a tree transfer is one call per node. Three phases, each
authenticated as a different account:

1. ``build_manifest`` — one traversal by any account that can see the tree,
   recording every node with its current owner.
2. ``do_chown`` — run as one source owner, over that owner's slice of the
   manifest. Same-organization Workspace accounts transfer outright; consumer
   accounts only get a pending-owner flag.
3. ``do_accept`` — run once as the target, accepting everything left pending by
   every source owner.

The manifest carries the result of each phase so a run is resumable and a
partial run is visible rather than assumed complete.
"""

from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional

from sheet_client import SheetsClient
from sheet_client.exceptions import SheetsAPIError

MANIFEST_VERSION = 1

# Drive's refusals that mean this pair of accounts must use the two-step
# consumer flow. The last one comes back when a pending offer already exists,
# which a resumed run hits on every node it already offered.
CONSENT_REASONS = (
    'consentRequiredForOwnershipTransfer',
    'cannotTransferOwnershipToNonWorkspaceUser',
    'ONLY_PENDING_OWNER_CAN_BECOME_NEW_OWNER',
)


def build_manifest(client: SheetsClient, root_id: str) -> Dict[str, Any]:
    """Inventory ``root_id`` and its descendants, grouped by current owner."""
    nodes = client.walk_tree(root_id)
    return {
        'version': MANIFEST_VERSION,
        'root': root_id,
        'surveyed_by': client.whoami().get('emailAddress'),
        'owners': owner_counts(nodes),
        'nodes': nodes,
    }


def owner_counts(nodes: List[dict]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for node in nodes:
        owner = node.get('owner') or '(unknown)'
        counts[owner] = counts.get(owner, 0) + 1
    return counts


def load_manifest(path: str) -> Dict[str, Any]:
    with open(path) as fh:
        manifest = json.load(fh)
    if manifest.get('version') != MANIFEST_VERSION:
        raise ValueError(f"unsupported manifest version {manifest.get('version')!r}")
    return manifest


def save_manifest(manifest: Dict[str, Any], path: str) -> None:
    with open(path, 'w') as fh:
        json.dump(manifest, fh, indent=2)


def plan_transfer(manifest: Dict[str, Any], to_email: str,
                  authenticated: Any = frozenset()) -> Dict[str, Any]:
    """Report which accounts must run ``chown`` to finish a transfer.

    Reads the manifest only — no Drive calls. ``authenticated`` is the set of
    addresses that already have a cached token, so the report can say which
    logins are still missing.
    """
    owners: Dict[str, Dict[str, Any]] = {}
    shared_drive: List[dict] = []
    unknown_owner: List[dict] = []
    shortcuts: List[dict] = []
    already_owned = 0

    for node in manifest['nodes']:
        stub = {'id': node['id'], 'name': node['name']}
        if node.get('shortcut_target'):
            shortcuts.append(dict(stub, target=node['shortcut_target']))
            continue
        if node.get('shared_drive'):
            shared_drive.append(stub)
            continue
        owner = node.get('owner')
        if not owner:
            unknown_owner.append(stub)
            continue
        if owner.lower() == to_email.lower():
            already_owned += 1
            continue
        record = owners.setdefault(owner, {'email': owner, 'files': 0, 'folders': 0,
                                           'done': 0})
        if (node.get('transfer') or {}).get('state') == 'owned':
            record['done'] += 1
        elif node.get('is_folder'):
            record['folders'] += 1
        else:
            record['files'] += 1

    ranked = []
    for record in owners.values():
        record['remaining'] = record['files'] + record['folders']
        record['authenticated'] = record['email'] in authenticated
        ranked.append(record)
    ranked.sort(key=lambda r: (-r['remaining'], r['email']))

    remaining = sum(r['remaining'] for r in ranked)
    return {
        'root': manifest.get('root'),
        'target': to_email,
        'surveyed_by': manifest.get('surveyed_by'),
        'total_nodes': len(manifest['nodes']),
        'owners': ranked,
        'already_owned': already_owned,
        'remaining': remaining,
        'skipped': {'shared_drive': shared_drive, 'unknown_owner': unknown_owner,
                    'shortcut': shortcuts},
        'shortcuts': shortcuts,
        'logins_missing': [r['email'] for r in ranked if not r['authenticated']],
        # Worst case per node: a direct attempt, a permission create, the
        # pendingOwner update, then the accept.
        'api_calls_upper_bound': remaining * 4,
    }


def do_chown(client: SheetsClient, manifest: Dict[str, Any], to_email: str,
             from_owner: Optional[str] = None, mode: str = 'auto',
             notify: bool = True, dry_run: bool = False,
             pace: float = 0.0, limit: Optional[int] = None,
             only: Optional[Any] = None, progress: Optional[Any] = None,
             checkpoint: Optional[Any] = None, checkpoint_every: int = 25,
             accept_client: Optional[SheetsClient] = None) -> Dict[str, Any]:
    """Offer or hand over every node owned by ``from_owner`` to ``to_email``.

    ``mode`` is ``auto`` (try the one-call Workspace path, fall back to pending),
    ``direct`` (Workspace only), or ``pending`` (consumer two-step). Must run
    authenticated as ``from_owner``; Drive rejects the call otherwise.
    """
    if mode not in ('auto', 'direct', 'pending'):
        raise ValueError(f"unknown mode {mode!r} (expected auto, direct, or pending)")
    if from_owner is None:
        from_owner = client.whoami().get('emailAddress')

    todo = _count_todo(manifest, from_owner, to_email, only, limit)
    tracker = _Progress(todo, progress)

    results = []
    touched = 0
    for node in manifest['nodes']:
        if only and node['id'] not in only:
            continue
        if limit is not None and touched >= limit:
            break
        outcome = _chown_node(client, node, to_email, from_owner, mode, notify, dry_run)
        if outcome is None:
            continue
        if accept_client and outcome['state'] == 'pending':
            outcome = _accept_node(accept_client, node, to_email)
        if not dry_run:
            node['transfer'] = outcome
        results.append(dict(outcome, id=node['id'], name=node['name']))
        if outcome['state'] in ('pending', 'owned', 'failed', 'would-transfer'):
            touched += 1
            tracker.step(outcome['state'], node)
            if checkpoint and not dry_run and touched % checkpoint_every == 0:
                checkpoint()
            if pace and not dry_run:
                time.sleep(pace)
    summary = _summarize(results, dry_run=dry_run, actor=from_owner, target=to_email)
    if limit is not None:
        summary['limited_to'] = limit
    return summary


def _chown_node(client: SheetsClient, node: dict, to_email: str, from_owner: str,
                mode: str, notify: bool, dry_run: bool) -> Optional[dict]:
    if node.get('shortcut_target'):
        # Drive refuses transferOwnership on a shortcut outright: "The action
        # cannot be performed on an item of mime-type ...shortcut".
        return {'state': 'skipped', 'reason': 'shortcuts cannot change owner'}
    if node.get('shared_drive'):
        return {'state': 'skipped', 'reason': 'shared drive owns this file'}
    if (node.get('transfer') or {}).get('state') == 'owned':
        return {'state': 'owned', 'reason': 'transferred by an earlier run'}
    if (node.get('owner') or '').lower() == to_email.lower():
        return {'state': 'owned', 'reason': 'already owned by target'}
    if (node.get('owner') or '').lower() != from_owner.lower():
        return None
    if dry_run:
        return {'state': 'would-transfer', 'mode': mode}

    if mode in ('auto', 'direct'):
        try:
            client.transfer_ownership(node['id'], to_email)
            return {'state': 'owned', 'mode': 'direct'}
        except SheetsAPIError as e:
            if mode == 'direct' or not _needs_consent(e):
                return {'state': 'failed', 'mode': 'direct', 'error': str(e)}

    try:
        permission = client.offer_ownership(node['id'], to_email, notify=notify)
    except SheetsAPIError as e:
        return {'state': 'failed', 'mode': 'pending', 'error': str(e)}

    # Drive has dropped this flag while returning 200. An unflagged permission
    # is a plain writer grant that accept cannot act on, so treat it as failure
    # here rather than letting the accept pass discover it.
    if not permission.get('pendingOwner'):
        return {'state': 'failed', 'mode': 'pending',
                'error': 'Drive did not set pendingOwner on the permission'}
    return {'state': 'pending', 'mode': 'pending'}


def _accept_node(client: SheetsClient, node: dict, as_email: str) -> dict:
    """Accept one pending offer, retrying once for the flag to become visible."""
    for attempt in (0, 1):
        try:
            client.accept_ownership(node['id'], as_email)
            return {'state': 'owned', 'mode': 'accepted'}
        except SheetsAPIError as e:
            if attempt == 0 and 'insufficientFilePermissions' in str(e):
                time.sleep(1)
                continue
            return {'state': 'failed-accept', 'error': str(e)}
    return {'state': 'failed-accept', 'error': 'unreachable'}


def do_accept(client: SheetsClient, manifest: Dict[str, Any],
              as_email: Optional[str] = None, dry_run: bool = False,
              pace: float = 0.0, progress: Optional[Any] = None,
              checkpoint: Optional[Any] = None,
              checkpoint_every: int = 25) -> Dict[str, Any]:
    """Accept every pending transfer in the manifest, as the new owner.

    Sweeps all source owners in one pass — the accepting account is the same for
    every node regardless of who offered it.
    """
    if as_email is None:
        as_email = client.whoami().get('emailAddress')

    pending = [n for n in manifest['nodes']
               if (n.get('transfer') or {}).get('state') in ('pending', 'failed-accept')]
    tracker = _Progress(len(pending), progress)

    results = []
    for node in manifest['nodes']:
        state = (node.get('transfer') or {}).get('state')
        if state not in ('pending', 'failed-accept'):
            continue
        if dry_run:
            results.append({'id': node['id'], 'name': node['name'],
                            'state': 'would-accept'})
            continue
        outcome = _accept_node(client, node, as_email)
        node['transfer'] = outcome
        results.append(dict(outcome, id=node['id'], name=node['name']))
        tracker.step(outcome['state'], node)
        if checkpoint and len(results) % checkpoint_every == 0:
            checkpoint()
        if pace:
            time.sleep(pace)
    return _summarize(results, dry_run=dry_run, actor=as_email, target=as_email)


def _count_todo(manifest: Dict[str, Any], from_owner: str, to_email: str,
                only: Optional[Any], limit: Optional[int]) -> int:
    """How many nodes this pass will act on, for the progress line's total."""
    count = 0
    for node in manifest['nodes']:
        if only and node['id'] not in only:
            continue
        if node.get('shared_drive') or node.get('shortcut_target'):
            continue
        if (node.get('transfer') or {}).get('state') == 'owned':
            continue
        owner = (node.get('owner') or '').lower()
        if owner == to_email.lower() or owner != from_owner.lower():
            continue
        count += 1
    return min(count, limit) if limit is not None else count


class _Progress:
    """Emits one line per node: position, rate, and remaining time."""

    def __init__(self, total: int, sink: Optional[Any]):
        self.total = total
        self.sink = sink
        self.done = 0
        self.started = time.monotonic()

    def step(self, state: str, node: dict) -> None:
        self.done += 1
        if not self.sink:
            return
        elapsed = time.monotonic() - self.started
        rate = self.done / elapsed if elapsed else 0.0
        left = (self.total - self.done) / rate if rate else 0.0
        kind = 'folder' if node.get('is_folder') else 'file'
        self.sink(f"[{self.done:>5}/{self.total}] {state:<14} {kind:<6} "
                  f"{node['name'][:44]:<46} {_hms(elapsed)} elapsed, "
                  f"{_hms(left)} left")


def _hms(seconds: float) -> str:
    seconds = int(seconds)
    return f"{seconds // 3600}h{(seconds % 3600) // 60:02d}m{seconds % 60:02d}s"


def _needs_consent(error: SheetsAPIError) -> bool:
    text = f"{error} {getattr(error, 'response', '')}"
    return any(reason in text for reason in CONSENT_REASONS)


def _summarize(results: List[dict], dry_run: bool, actor: Optional[str],
               target: Optional[str]) -> Dict[str, Any]:
    counts: Dict[str, int] = {}
    for r in results:
        counts[r['state']] = counts.get(r['state'], 0) + 1
    return {
        'actor': actor,
        'target': target,
        'dry_run': dry_run,
        'counts': counts,
        'results': results,
    }
