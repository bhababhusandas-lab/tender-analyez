import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException

from app.api.v1 import tender_analysis


class _RunningTask:
    def __init__(self):
        self.cancelled = False

    def done(self):
        return False

    def cancel(self):
        self.cancelled = True


class AnalysisCancellationTests(unittest.IsolatedAsyncioTestCase):
    async def test_cancel_marks_job_and_stops_background_task(self):
        task = _RunningTask()
        tender_analysis._PIPELINE_TASKS["job-1"] = task
        try:
            with patch.object(tender_analysis, "cancel_job", return_value=True) as cancel_job:
                result = await tender_analysis.cancel_tender_analysis(
                    "job-1", SimpleNamespace(id=42)
                )
            cancel_job.assert_called_once_with("job-1", 42, "pipeline")
            self.assertTrue(task.cancelled)
            self.assertEqual(result, {"status": "cancelled", "job_id": "job-1"})
        finally:
            tender_analysis._PIPELINE_TASKS.pop("job-1", None)

    async def test_cancel_rejects_unknown_job(self):
        with patch.object(tender_analysis, "cancel_job", return_value=False):
            with self.assertRaises(HTTPException) as raised:
                await tender_analysis.cancel_tender_analysis(
                    "missing", SimpleNamespace(id=42)
                )
        self.assertEqual(raised.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
