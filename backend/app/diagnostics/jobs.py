"""Bounded background jobs with progress and cancellation (in-process, local use)."""
import threading
import time
import traceback
import uuid

MAX_JOBS = 32
_jobs = {}
_lock = threading.Lock()


def start(kind, work, *, label=''):
    """Run work(progress, cancel) in a thread; returns the job id."""
    job_id = uuid.uuid4().hex[:12]
    cancel = threading.Event()
    record = {'id': job_id, 'kind': kind, 'label': label, 'state': 'running', 'done': 0, 'total': 1,
              'step': 'Starting', 'started': time.time(), 'finished': None, 'result_id': None, 'error': None,
              '_cancel': cancel}

    def progress(done, total, step):
        record.update(done=done, total=max(total, 1), step=step)

    def run():
        try:
            result_id = work(progress, cancel)
            record.update(state='cancelled' if cancel.is_set() and result_id is None else 'finished', result_id=result_id)
        except Exception as error:  # noqa: BLE001 - reported to the caller, not swallowed
            from .inverse import Cancelled
            if isinstance(error, Cancelled):
                record.update(state='cancelled', step='Cancelled')
            else:
                record.update(state='failed', error=str(error) or error.__class__.__name__,
                              trace=traceback.format_exc(limit=3))
        finally:
            record['finished'] = time.time()
    with _lock:
        finished = sorted((j for j in _jobs.values() if j['state'] != 'running'), key=lambda j: j['started'])
        while len(_jobs) >= MAX_JOBS and finished:
            _jobs.pop(finished.pop(0)['id'], None)
        if sum(j['state'] == 'running' for j in _jobs.values()) >= 4:
            raise ValueError('Four analyses are already running. Wait for one to finish or cancel it.')
        _jobs[job_id] = record
    threading.Thread(target=run, name=f'diagnostics-{kind}-{job_id}', daemon=True).start()
    return job_id


def view(job_id):
    job = _jobs.get(job_id)
    if job is None:
        raise KeyError(job_id)
    return {k: v for k, v in job.items() if not k.startswith('_') and k != 'trace'}


def cancel(job_id):
    job = _jobs.get(job_id)
    if job is None:
        raise KeyError(job_id)
    job['_cancel'].set()
    return view(job_id)


def wait(job_id, timeout=120.):
    """Testing helper: block until the job leaves the running state."""
    end = time.time() + timeout
    while time.time() < end:
        if _jobs[job_id]['state'] != 'running':
            return view(job_id)
        time.sleep(.05)
    raise TimeoutError(job_id)
