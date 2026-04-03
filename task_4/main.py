import redis
import pickle
import uuid
import time
import json
import multiprocessing
import traceback

class TaskProducer:
    def __init__(self, redis_host='localhost', redis_port=6379):
        self.redis = redis.Redis(host=redis_host, port=redis_port, db=0)

    def enqueue(self, func, *args, max_retries=3, **kwargs):
        task_id = str(uuid.uuid4())
        
        task_payload = {
            'task_id': task_id,
            'func': pickle.dumps(func),
            'args': pickle.dumps(args),
            'kwargs': pickle.dumps(kwargs),
            'retries': 0,
            'max_retries': max_retries
        }
        
        metadata = {
            'status': 'PENDING',
            'retries': 0,
            'created_at': time.time(),
            'duration': 0.0
        }
        self.redis.hset('task_metadata', task_id, json.dumps(metadata))
        
        self.redis.lpush('task_queue', pickle.dumps(task_payload))
        return task_id

class Worker(multiprocessing.Process):
    def __init__(self, worker_id, redis_host='localhost', redis_port=6379):
        super().__init__()
        self.worker_id = worker_id
        self.redis_host = redis_host
        self.redis_port = redis_port

    def run(self):
        self.redis = redis.Redis(host=self.redis_host, port=self.redis_port, db=0)
        print(f"[Worker-{self.worker_id}] Started polling...")
        
        while True:
            self._process_delayed_tasks()
            
            task_data = self.redis.rpop('task_queue')
            if not task_data:
                time.sleep(0.5)
                continue

            self._execute_task(pickle.loads(task_data))

    def _process_delayed_tasks(self):
        """Moves tasks whose backoff time has expired back to the main queue."""
        now = time.time()
        # Fetch tasks that are ready to be retried
        ready_tasks = self.redis.zrangebyscore('delayed_tasks', 0, now)
        
        for task_data in ready_tasks:
            # Atomic check: zrem returns 1 if it successfully removed the item.
            # This prevents multiple workers from queueing the same delayed task.
            if self.redis.zrem('delayed_tasks', task_data) > 0:
                self.redis.lpush('task_queue', task_data)

    def _execute_task(self, task):
        task_id = task['task_id']
        func = pickle.loads(task['func'])
        args = pickle.loads(task['args'])
        kwargs = pickle.loads(task['kwargs'])

        self._update_status(task_id, 'RUNNING')
        start_time = time.time()

        try:
            # Execute the callable
            result = func(*args, **kwargs)
            duration = time.time() - start_time
            
            # Save to Result Backend
            self.redis.hset('results', task_id, pickle.dumps(result))
            self._update_status(task_id, 'COMPLETED', duration=duration)
            print(f"[Worker-{self.worker_id}] Task {task_id[:8]}... COMPLETED.")

        except Exception as e:
            duration = time.time() - start_time
            task['retries'] += 1

            if task['retries'] <= task['max_retries']:
                # Exponential Backoff Algorithm: delay = 2 ^ retries
                delay = 2 ** task['retries']
                retry_at = time.time() + delay
                
                self._update_status(task_id, 'RETRYING', retries=task['retries'], duration=duration)
                
                # Push to Redis Sorted Set with the timestamp as the score
                self.redis.zadd('delayed_tasks', {pickle.dumps(task): retry_at})
                print(f"[Worker-{self.worker_id}] Task {task_id[:8]}... FAILED. Retrying in {delay}s.")
            else:
                # Dead-Letter Queue (DLQ) routing
                self._update_status(task_id, 'FAILED', retries=task['retries'], duration=duration)
                dlq_payload = {
                    'task_id': task_id,
                    'error': str(e),
                    'traceback': traceback.format_exc(),
                    'failed_at': time.time()
                }
                self.redis.lpush('dlq', pickle.dumps(dlq_payload))
                print(f"[Worker-{self.worker_id}] Task {task_id[:8]}... PERMANENTLY FAILED. Sent to DLQ.")

    def _update_status(self, task_id, status, retries=None, duration=None):
        meta_json = self.redis.hget('task_metadata', task_id)
        if meta_json:
            meta = json.loads(meta_json)
            meta['status'] = status
            if retries is not None:
                meta['retries'] = retries
            if duration is not None:
                meta['duration'] += duration
            self.redis.hset('task_metadata', task_id, json.dumps(meta))

class Dashboard:
    def __init__(self, redis_host='localhost', redis_port=6379):
        self.redis = redis.Redis(host=redis_host, port=redis_port, db=0)

    def display(self):
        print("\n" + "="*80)
        print(f"{'TASK QUEUE DASHBOARD':^80}")
        print("="*80)
        
        metadata = self.redis.hgetall('task_metadata')
        print(f"{'Task ID':<38} | {'Status':<12} | {'Retries':<7} | {'Duration (s)':<12}")
        print("-" * 80)
        
        for tid, m_bytes in metadata.items():
            task_id = tid.decode()
            meta = json.loads(m_bytes)
            duration = round(meta.get('duration', 0), 4)
            print(f"{task_id:<38} | {meta['status']:<12} | {meta['retries']:<7} | {duration:<12}")

        dlq_len = self.redis.llen('dlq')
        main_q_len = self.redis.llen('task_queue')
        delayed_q_len = self.redis.zcard('delayed_tasks')
        
        print("-" * 80)
        print(f"Queue Lengths -> Main: {main_q_len} | Delayed (Backoff): {delayed_q_len} | DLQ: {dlq_len}")
        print("="*80 + "\n")


# Dummy tasks for testing
def successful_task(x, y):
    time.sleep(1) # Simulate work
    return x + y

def flaky_task():
    # Simulate a task that occasionally fails
    import random
    if random.random() < 0.7:
        raise ConnectionError("Network timeout!")
    time.sleep(0.5)
    return "Finally succeeded!"

def doomed_task():
    time.sleep(0.2)
    raise ValueError("This will never work.")

if __name__ == '__main__':
    # 1. Clear Redis for a fresh run
    r = redis.Redis()
    r.flushall()

    # 2. Start Workers
    workers = []
    for i in range(3):
        w = Worker(worker_id=i+1)
        w.daemon = True
        w.start()
        workers.append(w)

    # 3. Producer Enqueues Tasks
    producer = TaskProducer()
    print("\n--- Enqueuing Tasks ---")
    producer.enqueue(successful_task, 10, 20)
    producer.enqueue(successful_task, 50, 100)
    producer.enqueue(flaky_task, max_retries=4)
    producer.enqueue(doomed_task, max_retries=2)

    # 4. Dashboard Polling Loop
    dash = Dashboard()
    try:
        # Let it run for 15 seconds to observe backoff and DLQ routing
        for _ in range(15):
            dash.display()
            time.sleep(1.5)
    except KeyboardInterrupt:
        pass
    finally:
        for w in workers:
            w.terminate()
        print("System shutdown complete.")