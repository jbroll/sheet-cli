"""Tests for drive_cli.transfer and the client's ownership methods."""

import json
import os
import sys
from unittest.mock import MagicMock, call, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from sheet_client import SheetsClient
from sheet_client.auth import token_path_for
from sheet_client.exceptions import SheetsAPIError
from drive_cli import transfer

FOLDER_MIME = "application/vnd.google-apps.folder"

ALICE = "alice@example.com"
BOB = "bob@example.com"
CARL = "carl@example.com"


def node(id_, owner, **kw):
    base = {"id": id_, "name": id_.lower(), "mimeType": "application/pdf",
            "parents": ["ROOT"], "owner": owner, "depth": 1, "is_folder": False,
            "shortcut_target": None, "shared_drive": False, "can_share": True}
    base.update(kw)
    return base


def manifest(*nodes):
    return {"version": transfer.MANIFEST_VERSION, "root": "ROOT",
            "surveyed_by": BOB, "owners": transfer.owner_counts(list(nodes)),
            "nodes": list(nodes)}


def consent_error():
    return SheetsAPIError(
        "API error 403: consentRequiredForOwnershipTransfer", status_code=403)


@pytest.fixture
def client():
    c = MagicMock()
    c.whoami.return_value = {"emailAddress": ALICE}
    c.offer_ownership.return_value = {"id": "P", "role": "writer",
                                      "pendingOwner": True}
    return c


class TestBuildManifest:
    def test_groups_nodes_by_owner(self, client):
        client.walk_tree.return_value = [node("A", ALICE), node("B", CARL),
                                         node("C", ALICE)]
        m = transfer.build_manifest(client, "ROOT")
        assert m["owners"] == {ALICE: 2, CARL: 1}
        assert m["surveyed_by"] == ALICE
        assert len(m["nodes"]) == 3

    def test_unknown_owner_is_counted(self, client):
        client.walk_tree.return_value = [node("A", None)]
        assert transfer.build_manifest(client, "ROOT")["owners"] == {"(unknown)": 1}


class TestPlan:
    def test_lists_each_owner_biggest_first(self):
        m = manifest(node("A", ALICE), node("B", CARL, is_folder=True),
                     node("C", CARL), node("D", CARL))
        plan = transfer.plan_transfer(m, BOB)
        assert [o["email"] for o in plan["owners"]] == [CARL, ALICE]
        assert plan["owners"][0]["remaining"] == 3
        assert plan["owners"][0]["folders"] == 1
        assert plan["owners"][0]["files"] == 2
        assert plan["remaining"] == 4

    def test_target_owned_nodes_are_counted_not_assigned(self):
        plan = transfer.plan_transfer(manifest(node("A", BOB), node("B", ALICE)), BOB)
        assert plan["already_owned"] == 1
        assert [o["email"] for o in plan["owners"]] == [ALICE]

    def test_nodes_done_by_an_earlier_run_drop_out_of_remaining(self):
        done = node("A", ALICE)
        done["transfer"] = {"state": "owned"}
        plan = transfer.plan_transfer(manifest(done, node("B", ALICE)), BOB)
        assert plan["owners"][0] == {"email": ALICE, "files": 1, "folders": 0,
                                     "done": 1, "remaining": 1, "authenticated": False}

    def test_shared_drive_nodes_are_reported_as_untransferable(self):
        plan = transfer.plan_transfer(
            manifest(node("A", ALICE, shared_drive=True), node("B", ALICE)), BOB)
        assert [s["id"] for s in plan["skipped"]["shared_drive"]] == ["A"]
        assert plan["remaining"] == 1

    def test_invisible_owner_is_reported_separately(self):
        plan = transfer.plan_transfer(manifest(node("A", None)), BOB)
        assert [s["id"] for s in plan["skipped"]["unknown_owner"]] == ["A"]
        assert plan["owners"] == []

    def test_shortcuts_are_untransferable_not_pending_work(self):
        plan = transfer.plan_transfer(
            manifest(node("A", ALICE, shortcut_target="TARGET"), node("B", ALICE)), BOB)
        assert plan["shortcuts"] == [{"id": "A", "name": "a", "target": "TARGET"}]
        assert plan["skipped"]["shortcut"] == plan["shortcuts"]
        assert plan["remaining"] == 1
        assert plan["owners"][0]["remaining"] == 1

    def test_missing_logins_are_named(self):
        m = manifest(node("A", ALICE), node("B", CARL))
        plan = transfer.plan_transfer(m, BOB, authenticated={ALICE})
        assert plan["logins_missing"] == [CARL]
        assert {o["email"]: o["authenticated"] for o in plan["owners"]} == {
            ALICE: True, CARL: False}

    def test_call_estimate_tracks_remaining_work(self):
        plan = transfer.plan_transfer(manifest(node("A", ALICE), node("B", BOB)), BOB)
        assert plan["api_calls_upper_bound"] == 4

    def test_plan_makes_no_drive_calls(self, client):
        transfer.plan_transfer(manifest(node("A", ALICE)), BOB)
        client.assert_not_called()
        assert client.method_calls == []


class TestChownSelection:
    def test_only_touches_files_owned_by_from_owner(self, client):
        m = manifest(node("A", ALICE), node("B", CARL))
        transfer.do_chown(client, m, BOB, from_owner=ALICE, mode="direct")
        client.transfer_ownership.assert_called_once_with("A", BOB)

    def test_from_owner_defaults_to_authenticated_account(self, client):
        m = manifest(node("A", ALICE), node("B", CARL))
        summary = transfer.do_chown(client, m, BOB, mode="direct")
        assert summary["actor"] == ALICE
        client.transfer_ownership.assert_called_once_with("A", BOB)

    def test_already_owned_by_target_is_skipped(self, client):
        m = manifest(node("A", BOB))
        summary = transfer.do_chown(client, m, BOB, from_owner=ALICE)
        assert summary["counts"] == {"owned": 1}
        client.transfer_ownership.assert_not_called()

    def test_shortcut_is_skipped_without_calling_drive(self, client):
        m = manifest(node("A", ALICE, shortcut_target="T"))
        summary = transfer.do_chown(client, m, BOB, from_owner=ALICE)
        assert summary["counts"] == {"skipped": 1}
        assert "shortcut" in summary["results"][0]["reason"]
        client.transfer_ownership.assert_not_called()
        client.offer_ownership.assert_not_called()

    def test_shared_drive_node_is_skipped(self, client):
        m = manifest(node("A", ALICE, shared_drive=True))
        summary = transfer.do_chown(client, m, BOB, from_owner=ALICE)
        assert summary["counts"] == {"skipped": 1}
        client.transfer_ownership.assert_not_called()

    def test_node_transferred_by_an_earlier_run_is_skipped(self, client):
        n = node("A", ALICE)
        n["transfer"] = {"state": "owned"}
        summary = transfer.do_chown(client, manifest(n), BOB, from_owner=ALICE)
        assert summary["counts"] == {"owned": 1}
        client.transfer_ownership.assert_not_called()

    def test_rejects_unknown_mode(self, client):
        with pytest.raises(ValueError):
            transfer.do_chown(client, manifest(node("A", ALICE)), BOB, mode="sideways")


class TestChownModes:
    def test_direct_mode_records_owned(self, client):
        m = manifest(node("A", ALICE))
        summary = transfer.do_chown(client, m, BOB, from_owner=ALICE, mode="direct")
        assert summary["counts"] == {"owned": 1}
        assert m["nodes"][0]["transfer"]["mode"] == "direct"

    def test_direct_mode_does_not_fall_back(self, client):
        client.transfer_ownership.side_effect = consent_error()
        m = manifest(node("A", ALICE))
        summary = transfer.do_chown(client, m, BOB, from_owner=ALICE, mode="direct")
        assert summary["counts"] == {"failed": 1}
        client.offer_ownership.assert_not_called()

    def test_auto_falls_back_to_pending_on_consent_error(self, client):
        client.transfer_ownership.side_effect = consent_error()
        m = manifest(node("A", ALICE))
        summary = transfer.do_chown(client, m, BOB, from_owner=ALICE)
        assert summary["counts"] == {"pending": 1}
        client.offer_ownership.assert_called_once_with("A", BOB, notify=True)

    def test_auto_falls_back_when_an_offer_already_stands(self, client):
        client.transfer_ownership.side_effect = SheetsAPIError(
            'API error 400: "ONLY_PENDING_OWNER_CAN_BECOME_NEW_OWNER"', status_code=400)
        summary = transfer.do_chown(client, manifest(node("A", ALICE)), BOB,
                                    from_owner=ALICE)
        assert summary["counts"] == {"pending": 1}

    def test_auto_reports_other_errors_without_falling_back(self, client):
        client.transfer_ownership.side_effect = SheetsAPIError(
            "API error 404: File not found", status_code=404)
        m = manifest(node("A", ALICE))
        summary = transfer.do_chown(client, m, BOB, from_owner=ALICE)
        assert summary["counts"] == {"failed": 1}
        client.offer_ownership.assert_not_called()

    def test_pending_mode_skips_the_direct_attempt(self, client):
        m = manifest(node("A", ALICE))
        transfer.do_chown(client, m, BOB, from_owner=ALICE, mode="pending")
        client.transfer_ownership.assert_not_called()
        client.offer_ownership.assert_called_once_with("A", BOB, notify=True)

    def test_offer_that_lands_unflagged_is_a_failure_not_a_pending(self, client):
        client.offer_ownership.return_value = {"id": "P", "role": "writer",
                                               "pendingOwner": False}
        summary = transfer.do_chown(client, manifest(node("A", ALICE)), BOB,
                                    from_owner=ALICE, mode="pending")
        assert summary["counts"] == {"failed": 1}
        assert "pendingOwner" in summary["results"][0]["error"]

    def test_no_notify_is_passed_through(self, client):
        m = manifest(node("A", ALICE))
        transfer.do_chown(client, m, BOB, from_owner=ALICE, mode="pending", notify=False)
        client.offer_ownership.assert_called_once_with("A", BOB, notify=False)

    def test_dry_run_calls_nothing_and_leaves_manifest_clean(self, client):
        m = manifest(node("A", ALICE))
        summary = transfer.do_chown(client, m, BOB, from_owner=ALICE, dry_run=True)
        assert summary["counts"] == {"would-transfer": 1}
        assert "transfer" not in m["nodes"][0]
        client.transfer_ownership.assert_not_called()


class TestPacingAndSlicing:
    def test_limit_stops_after_n_nodes(self, client):
        m = manifest(*[node(f"N{i}", ALICE) for i in range(5)])
        summary = transfer.do_chown(client, m, BOB, from_owner=ALICE, mode="direct",
                                    limit=2)
        assert client.transfer_ownership.call_count == 2
        assert summary["limited_to"] == 2

    def test_limit_does_not_count_skipped_nodes(self, client):
        m = manifest(node("SKIP", CARL), node("A", ALICE), node("B", ALICE))
        transfer.do_chown(client, m, BOB, from_owner=ALICE, mode="direct", limit=2)
        assert client.transfer_ownership.call_count == 2

    def test_only_restricts_to_named_nodes(self, client):
        m = manifest(node("A", ALICE), node("B", ALICE), node("C", ALICE))
        transfer.do_chown(client, m, BOB, from_owner=ALICE, mode="direct",
                          only={"B"})
        client.transfer_ownership.assert_called_once_with("B", BOB)

    def test_pace_sleeps_between_nodes(self, client):
        m = manifest(node("A", ALICE), node("B", ALICE))
        with patch("drive_cli.transfer.time.sleep") as sleep:
            transfer.do_chown(client, m, BOB, from_owner=ALICE, mode="direct", pace=0.25)
        assert sleep.call_args_list == [call(0.25), call(0.25)]

    def test_pace_is_skipped_on_a_dry_run(self, client):
        m = manifest(node("A", ALICE))
        with patch("drive_cli.transfer.time.sleep") as sleep:
            transfer.do_chown(client, m, BOB, from_owner=ALICE, pace=0.25, dry_run=True)
        sleep.assert_not_called()

    def test_accept_paces_too(self, client):
        a = node("A", ALICE)
        a["transfer"] = {"state": "pending"}
        with patch("drive_cli.transfer.time.sleep") as sleep:
            transfer.do_accept(client, manifest(a), as_email=BOB, pace=0.5)
        sleep.assert_called_once_with(0.5)


class TestProgressAndCheckpoints:
    def test_emits_a_line_per_node_with_position_and_total(self, client):
        lines = []
        m = manifest(node("A", ALICE), node("B", ALICE, is_folder=True))
        transfer.do_chown(client, m, BOB, from_owner=ALICE, mode="direct",
                          progress=lines.append)
        assert len(lines) == 2
        assert lines[0].startswith("[    1/2] owned")
        assert "file" in lines[0] and "folder" in lines[1]
        assert "left" in lines[0]

    def test_total_counts_only_this_owners_remaining_work(self, client):
        lines = []
        done = node("C", ALICE)
        done["transfer"] = {"state": "owned"}
        m = manifest(node("A", ALICE), node("B", CARL), done,
                     node("D", ALICE, shared_drive=True),
                     node("E", ALICE, shortcut_target="T"))
        transfer.do_chown(client, m, BOB, from_owner=ALICE, mode="direct",
                          progress=lines.append)
        assert lines[0].startswith("[    1/1]")

    def test_limit_shrinks_the_total(self, client):
        lines = []
        m = manifest(*[node(f"N{i}", ALICE) for i in range(9)])
        transfer.do_chown(client, m, BOB, from_owner=ALICE, mode="direct",
                          limit=3, progress=lines.append)
        assert lines[0].startswith("[    1/3]")
        assert len(lines) == 3

    def test_checkpoint_saves_partway_through(self, client):
        saves = []
        m = manifest(*[node(f"N{i}", ALICE) for i in range(5)])
        transfer.do_chown(client, m, BOB, from_owner=ALICE, mode="direct",
                          checkpoint=lambda: saves.append(True), checkpoint_every=2)
        assert len(saves) == 2

    def test_a_checkpoint_holds_what_ran_before_a_crash(self, client):
        m = manifest(node("A", ALICE), node("B", ALICE), node("C", ALICE))
        client.transfer_ownership.side_effect = [None, RuntimeError("connection lost")]
        saved = {}
        with pytest.raises(RuntimeError):
            transfer.do_chown(client, m, BOB, from_owner=ALICE, mode="direct",
                              checkpoint=lambda: saved.update(json.loads(json.dumps(m))),
                              checkpoint_every=1)
        assert saved["nodes"][0]["transfer"]["state"] == "owned"

    def test_accept_reports_progress_and_checkpoints(self, client):
        lines, saves = [], []
        nodes = []
        for i in range(3):
            n = node(f"N{i}", ALICE)
            n["transfer"] = {"state": "pending"}
            nodes.append(n)
        transfer.do_accept(client, manifest(*nodes), as_email=BOB,
                           progress=lines.append,
                           checkpoint=lambda: saves.append(True), checkpoint_every=2)
        assert lines[0].startswith("[    1/3] owned")
        assert len(saves) == 1

    def test_no_sink_means_no_progress_work(self, client):
        m = manifest(node("A", ALICE))
        transfer.do_chown(client, m, BOB, from_owner=ALICE, mode="direct", progress=None)


class TestPairedMode:
    @pytest.fixture
    def target(self):
        return MagicMock()

    def test_each_offer_is_accepted_immediately(self, client, target):
        m = manifest(node("A", ALICE), node("B", ALICE))
        summary = transfer.do_chown(client, m, BOB, from_owner=ALICE, mode="pending",
                                    accept_client=target)
        assert summary["counts"] == {"owned": 2}
        assert target.accept_ownership.call_args_list == [call("A", BOB), call("B", BOB)]
        assert m["nodes"][0]["transfer"]["mode"] == "accepted"

    def test_a_direct_transfer_needs_no_accept(self, client, target):
        summary = transfer.do_chown(client, manifest(node("A", ALICE)), BOB,
                                    from_owner=ALICE, mode="direct",
                                    accept_client=target)
        assert summary["counts"] == {"owned": 1}
        target.accept_ownership.assert_not_called()

    def test_a_failed_offer_is_not_accepted(self, client, target):
        client.offer_ownership.return_value = {"id": "P", "pendingOwner": False}
        transfer.do_chown(client, manifest(node("A", ALICE)), BOB, from_owner=ALICE,
                          mode="pending", accept_client=target)
        target.accept_ownership.assert_not_called()

    def test_accept_retries_once_while_the_flag_lands(self, client, target):
        target.accept_ownership.side_effect = [
            SheetsAPIError("API error 403: insufficientFilePermissions", status_code=403),
            None]
        with patch("drive_cli.transfer.time.sleep"):
            summary = transfer.do_chown(client, manifest(node("A", ALICE)), BOB,
                                        from_owner=ALICE, mode="pending",
                                        accept_client=target)
        assert summary["counts"] == {"owned": 1}
        assert target.accept_ownership.call_count == 2

    def test_a_persistent_refusal_stops_after_one_retry(self, client, target):
        target.accept_ownership.side_effect = SheetsAPIError(
            "API error 403: insufficientFilePermissions", status_code=403)
        with patch("drive_cli.transfer.time.sleep"):
            summary = transfer.do_chown(client, manifest(node("A", ALICE)), BOB,
                                        from_owner=ALICE, mode="pending",
                                        accept_client=target)
        assert summary["counts"] == {"failed-accept": 1}
        assert target.accept_ownership.call_count == 2

    def test_other_accept_errors_do_not_retry(self, client, target):
        target.accept_ownership.side_effect = SheetsAPIError(
            "API error 404: File not found", status_code=404)
        summary = transfer.do_chown(client, manifest(node("A", ALICE)), BOB,
                                    from_owner=ALICE, mode="pending",
                                    accept_client=target)
        assert summary["counts"] == {"failed-accept": 1}
        assert target.accept_ownership.call_count == 1

    def test_paired_failures_stay_resumable_by_the_accept_pass(self, client, target):
        target.accept_ownership.side_effect = SheetsAPIError("API error 500", 500)
        m = manifest(node("A", ALICE))
        transfer.do_chown(client, m, BOB, from_owner=ALICE, mode="pending",
                          accept_client=target)
        target.accept_ownership.side_effect = None
        assert transfer.do_accept(target, m, as_email=BOB)["counts"] == {"owned": 1}


class TestAccept:
    def test_accepts_only_pending_nodes(self, client):
        client.whoami.return_value = {"emailAddress": BOB}
        a, b, c = node("A", ALICE), node("B", CARL), node("C", ALICE)
        a["transfer"] = {"state": "pending"}
        b["transfer"] = {"state": "pending"}
        c["transfer"] = {"state": "owned"}
        summary = transfer.do_accept(client, manifest(a, b, c))
        assert summary["counts"] == {"owned": 2}
        assert client.accept_ownership.call_count == 2

    def test_one_pass_covers_every_source_owner(self, client):
        a, b = node("A", ALICE), node("B", CARL)
        a["transfer"] = b["transfer"] = {"state": "pending"}
        transfer.do_accept(client, manifest(a, b), as_email=BOB)
        client.accept_ownership.assert_any_call("A", BOB)
        client.accept_ownership.assert_any_call("B", BOB)

    def test_failure_is_recorded_and_retried_next_run(self, client):
        a = node("A", ALICE)
        a["transfer"] = {"state": "pending"}
        m = manifest(a)
        client.accept_ownership.side_effect = SheetsAPIError("API error 403: nope",
                                                            status_code=403)
        summary = transfer.do_accept(client, m, as_email=BOB)
        assert summary["counts"] == {"failed-accept": 1}

        client.accept_ownership.side_effect = None
        assert transfer.do_accept(client, m, as_email=BOB)["counts"] == {"owned": 1}

    def test_untouched_nodes_are_ignored(self, client):
        summary = transfer.do_accept(client, manifest(node("A", ALICE)), as_email=BOB)
        assert summary["counts"] == {}
        client.accept_ownership.assert_not_called()

    def test_dry_run_calls_nothing(self, client):
        a = node("A", ALICE)
        a["transfer"] = {"state": "pending"}
        summary = transfer.do_accept(client, manifest(a), as_email=BOB, dry_run=True)
        assert summary["counts"] == {"would-accept": 1}
        client.accept_ownership.assert_not_called()


class TestManifestFile:
    def test_round_trip(self, tmp_path):
        m = manifest(node("A", ALICE))
        path = str(tmp_path / "m.json")
        transfer.save_manifest(m, path)
        assert transfer.load_manifest(path) == m

    def test_rejects_foreign_version(self, tmp_path):
        path = tmp_path / "m.json"
        path.write_text(json.dumps({"version": 99, "nodes": []}))
        with pytest.raises(ValueError):
            transfer.load_manifest(str(path))


class TestTokenPathPerAccount:
    def test_none_keeps_the_default_token(self):
        assert token_path_for(None) is None

    def test_each_account_gets_its_own_file(self):
        assert token_path_for(ALICE) != token_path_for(BOB)
        assert token_path_for(ALICE).endswith("token-alice@example.com.json")

    def test_path_separators_are_neutralized(self):
        assert "/" not in os.path.basename(token_path_for("../../etc/passwd"))


@pytest.fixture
def real_client():
    with patch('sheet_client.client.get_credentials'), \
         patch('sheet_client.client.build'):
        c = SheetsClient()
    c.drive = MagicMock()
    return c


class TestClientOwnership:
    def test_walk_tree_recurses_into_subfolders(self, real_client):
        real_client.drive.files().get().execute.return_value = {
            "id": "ROOT", "name": "root", "mimeType": FOLDER_MIME,
            "owners": [{"emailAddress": ALICE}]}
        real_client._list_tree_children = MagicMock(side_effect=[
            [{"id": "SUB", "name": "sub", "mimeType": FOLDER_MIME,
              "owners": [{"emailAddress": CARL}]}],
            [{"id": "FILE", "name": "f", "mimeType": "application/pdf",
              "owners": [{"emailAddress": ALICE}]}],
        ])
        nodes = real_client.walk_tree("ROOT")
        assert [n["id"] for n in nodes] == ["ROOT", "SUB", "FILE"]
        assert [n["depth"] for n in nodes] == [0, 1, 2]
        assert nodes[1]["owner"] == CARL

    def test_walk_tree_does_not_revisit_a_node(self, real_client):
        real_client.drive.files().get().execute.return_value = {
            "id": "ROOT", "name": "root", "mimeType": FOLDER_MIME,
            "owners": [{"emailAddress": ALICE}]}
        child = {"id": "FILE", "name": "f", "mimeType": "application/pdf",
                 "owners": [{"emailAddress": ALICE}]}
        real_client._list_tree_children = MagicMock(return_value=[child, child])
        assert len(real_client.walk_tree("ROOT")) == 2

    def test_offer_ownership_updates_an_existing_permission(self, real_client):
        real_client._permission_for = MagicMock(return_value={"id": "PERM1"})
        real_client._execute_with_retry = MagicMock(return_value={})
        real_client.offer_ownership("A", BOB)
        kwargs = real_client.drive.permissions().update.call_args.kwargs
        assert kwargs["permissionId"] == "PERM1"
        assert kwargs["body"] == {"role": "writer", "pendingOwner": True}

    def test_offer_ownership_creates_then_flags_when_none_exists(self, real_client):
        real_client._permission_for = MagicMock(return_value=None)
        real_client._execute_with_retry = MagicMock(return_value={"id": "PERM2"})
        real_client.offer_ownership("A", BOB, notify=False)

        created = real_client.drive.permissions().create.call_args.kwargs
        assert created["sendNotificationEmail"] is False
        assert "pendingOwner" not in created["body"]

        # permissions.create drops pendingOwner, so the flag needs its own update.
        updated = real_client.drive.permissions().update.call_args.kwargs
        assert updated["permissionId"] == "PERM2"
        assert updated["body"] == {"role": "writer", "pendingOwner": True}

    def test_accept_ownership_sets_transfer_flag(self, real_client):
        real_client._permission_for = MagicMock(return_value={"id": "PERM1"})
        real_client._execute_with_retry = MagicMock(return_value={})
        real_client.accept_ownership("A", BOB)
        kwargs = real_client.drive.permissions().update.call_args.kwargs
        assert kwargs["transferOwnership"] is True
        assert kwargs["body"] == {"role": "owner"}

    def test_permission_for_matches_case_insensitively(self, real_client):
        real_client.list_permissions = MagicMock(
            return_value=[{"id": "P", "emailAddress": "BOB@Example.com"}])
        assert real_client._permission_for("A", BOB)["id"] == "P"

    def test_permission_for_survives_an_unlistable_file(self, real_client):
        real_client.list_permissions = MagicMock(
            side_effect=SheetsAPIError("API error 403", status_code=403))
        assert real_client._permission_for("A", BOB) is None
