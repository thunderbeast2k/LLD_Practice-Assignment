import os
import tempfile
import unittest

from lld_practice.domain import (Attempt, AttemptStatus, InvalidTransition, NotFoundError, ValidationError)
from lld_practice.jobs import InlineRunner
from lld_practice.storage import InMemoryRepository, SQLiteRepository
from tests.helpers import Boom, Flaky, example, make_service

GOOD, BAD = example("parking_lot_good.py"), example("parking_lot_god_class.py")


class RecordingRunner(InlineRunner):
    """Queues jobs so tests can observe the intermediate SUBMITTED state."""
    def __init__(self): self.jobs = []
    def submit(self, fn, *args): self.jobs.append((fn, args))
    def run_all(self):
        while self.jobs:
            fn, args = self.jobs.pop(0)
            fn(*args)


class AttemptStateMachineTests(unittest.TestCase):
    def test_cannot_submit_empty(self):
        with self.assertRaises(ValidationError):
            Attempt("l", "p").submit()

    def test_cannot_edit_after_submit(self):
        a = Attempt("l", "p", content="x")
        a.submit()
        with self.assertRaises(InvalidTransition):
            a.save_draft("y", "python")

    def test_cannot_complete_without_evaluating(self):
        with self.assertRaises(InvalidTransition):
            Attempt("l", "p", content="x").fail("nope")

    def test_roundtrip_serialisation(self):
        s = make_service()
        a = s.start_attempt("l", "parking-lot")
        s.save_draft(a.id, GOOD, "python", "because")
        s.submit(a.id)
        stored = s.repo.get(a.id)
        self.assertEqual(Attempt.from_dict(stored.to_dict()).to_dict(), stored.to_dict())


class JourneyTests(unittest.TestCase):
    def setUp(self):
        self.s = make_service()

    def test_full_journey_with_history_and_improvement(self):
        a1 = self.s.start_attempt("amy", "parking-lot")
        self.assertEqual(a1.number, 1)
        self.s.save_draft(a1.id, BAD, "python")
        self.s.submit(a1.id)
        first = self.s.get_attempt(a1.id)
        self.assertEqual(first["status"], "COMPLETED")
        self.assertIsNone(first["previous"])

        a2 = self.s.start_attempt("amy", "parking-lot", based_on=a1.id)  # "try again"
        self.assertEqual((a2.number, a2.content, a2.based_on), (2, BAD, a1.id))
        self.s.save_draft(a2.id, GOOD, "python", "Strategy for pricing and allocation")
        self.s.submit(a2.id)
        second = self.s.get_attempt(a2.id)
        self.assertGreater(second["feedback"]["overall"], first["feedback"]["overall"])
        self.assertEqual(second["previous"]["number"], 1)

        hist = self.s.history("amy")
        self.assertEqual([h["number"] for h in hist], [2, 1])  # newest first
        self.assertGreater(hist[0]["delta"], 0)
        self.assertIsNone(hist[1]["delta"])

    def test_history_is_per_learner_and_filterable(self):
        self.s.start_attempt("amy", "parking-lot")
        self.s.start_attempt("bob", "elevator")
        self.assertEqual(len(self.s.history("amy")), 1)
        self.assertEqual(self.s.history("amy", "elevator"), [])

    def test_cannot_base_attempt_on_someone_elses(self):
        a = self.s.start_attempt("amy", "parking-lot")
        with self.assertRaises(ValidationError):
            self.s.start_attempt("bob", "parking-lot", based_on=a.id)

    def test_unknown_problem_and_attempt(self):
        with self.assertRaises(NotFoundError):
            self.s.start_attempt("amy", "nope")
        with self.assertRaises(NotFoundError):
            self.s.get_attempt("missing")

    def test_unparseable_submission_is_rejected_and_stays_editable(self):
        a = self.s.start_attempt("amy", "parking-lot")
        self.s.save_draft(a.id, "class Broken(:\n    pass   # this will not parse at all", "python")
        with self.assertRaises(ValidationError):
            self.s.submit(a.id)
        self.assertEqual(self.s.repo.get(a.id).status, AttemptStatus.DRAFT)
        self.s.save_draft(a.id, GOOD, "python")  # fix and resubmit
        self.s.submit(a.id)
        self.assertEqual(self.s.repo.get(a.id).status, AttemptStatus.COMPLETED)

    def test_unknown_format_rejected(self):
        a = self.s.start_attempt("amy", "parking-lot")
        with self.assertRaises(ValidationError):
            self.s.save_draft(a.id, GOOD, "cobol")

    def test_double_submit_is_rejected(self):
        a = self.s.start_attempt("amy", "parking-lot")
        self.s.save_draft(a.id, GOOD, "python")
        self.s.submit(a.id)
        with self.assertRaises(InvalidTransition):
            self.s.submit(a.id)

    def test_text_format_journey(self):
        a = self.s.start_attempt("amy", "parking-lot")
        self.s.save_draft(a.id, example("parking_lot_text.txt"), "text")
        self.s.submit(a.id)
        self.assertEqual(self.s.get_attempt(a.id)["status"], "COMPLETED")


class AsyncAndFailureTests(unittest.TestCase):
    def test_status_visible_while_queued(self):
        runner = RecordingRunner()
        s = make_service(runner=runner)
        a = s.start_attempt("amy", "parking-lot")
        s.save_draft(a.id, GOOD, "python")
        s.submit(a.id)
        self.assertEqual(s.get_attempt(a.id)["status"], "SUBMITTED")
        runner.run_all()
        self.assertEqual(s.get_attempt(a.id)["status"], "COMPLETED")

    def test_ai_outage_gives_partial_then_retry_completes(self):
        flaky = Flaky(fail_times=1)
        s = make_service(extra=[flaky])
        a = s.start_attempt("amy", "parking-lot")
        s.save_draft(a.id, GOOD, "python")
        s.submit(a.id)
        got = s.get_attempt(a.id)
        self.assertEqual(got["status"], "PARTIAL")
        self.assertTrue(got["feedback"]["warnings"])
        s.retry(a.id)
        self.assertEqual(s.get_attempt(a.id)["status"], "COMPLETED")

    def test_total_failure_marks_failed_and_is_retryable(self):
        s = make_service(extra=[Flaky(fail_times=1)], rules=False)
        a = s.start_attempt("amy", "parking-lot")
        s.save_draft(a.id, GOOD, "python")
        s.submit(a.id)
        got = s.get_attempt(a.id)
        self.assertEqual(got["status"], "FAILED")
        self.assertIn("retry", got["error"].lower())
        self.assertEqual(got["content"], GOOD)  # work is never lost
        s.pipeline.evaluators.extend(make_service().pipeline.evaluators)  # "service recovers"
        s.retry(a.id)
        self.assertIn(s.get_attempt(a.id)["status"], ("COMPLETED", "PARTIAL"))

    def test_unexpected_crash_never_leaves_attempt_stuck(self):
        s = make_service()
        s.pipeline.run = lambda *a, **k: (_ for _ in ()).throw(MemoryError("boom"))
        a = s.start_attempt("amy", "parking-lot")
        s.save_draft(a.id, GOOD, "python")
        s.submit(a.id)
        got = s.get_attempt(a.id)
        self.assertEqual(got["status"], "FAILED")
        self.assertIn("MemoryError", got["error"])

    def test_retry_only_allowed_for_failed_or_partial(self):
        s = make_service()
        a = s.start_attempt("amy", "parking-lot")
        with self.assertRaises(InvalidTransition):
            s.retry(a.id)  # DRAFT
        s.save_draft(a.id, GOOD, "python")
        s.submit(a.id)
        with self.assertRaises(InvalidTransition):
            s.retry(a.id)  # COMPLETED

    def test_recover_interrupted_evaluations(self):
        s = make_service()
        a = s.start_attempt("amy", "parking-lot")
        s.save_draft(a.id, GOOD, "python")
        att = s.repo.get(a.id)
        att.submit()
        att.start_evaluation()  # simulate crash mid-evaluation
        s.repo.save(att)
        self.assertEqual(s.recover_interrupted(), 1)
        self.assertEqual(s.get_attempt(a.id)["status"], "FAILED")
        s.retry(a.id)
        self.assertEqual(s.get_attempt(a.id)["status"], "COMPLETED")


class RepositoryTests(unittest.TestCase):
    def check(self, repo):
        a = Attempt("amy", "parking-lot", content="x")
        repo.save(a)
        a.submit()
        repo.save(a)  # upsert
        self.assertEqual(repo.get(a.id).status, AttemptStatus.SUBMITTED)
        self.assertEqual(len(repo.list("amy")), 1)
        self.assertEqual(len(repo.list_by_status(AttemptStatus.SUBMITTED)), 1)
        with self.assertRaises(NotFoundError):
            repo.get("nope")

    def test_in_memory(self): self.check(InMemoryRepository())

    def test_sqlite(self): self.check(SQLiteRepository(":memory:"))

    def test_sqlite_persists_across_connections(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "t.db")
            a = Attempt("amy", "parking-lot", content="x")
            SQLiteRepository(path).save(a)
            self.assertEqual(SQLiteRepository(path).get(a.id).content, "x")
