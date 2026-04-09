import queue
import json

class JobLogger:
    """Manages real-time log queues for SSE (Server-Sent Events) clients."""
    
    def __init__(self):
        self.job_queues = {} # dict of list of queues per job_id
        self.job_history = {} # history of log strings per job_id

    def register_job(self, job_id):
        if job_id not in self.job_queues:
            self.job_queues[job_id] = []
            self.job_history[job_id] = []

    def get_queue(self, job_id):
        self.register_job(job_id)
        q = queue.Queue()
        self.job_queues[job_id].append(q)
        
        # Flush existing history to the new queue so clients connecting mid-job get the full story
        for record in self.job_history[job_id]:
            q.put(record)
            
        return q

    def log(self, job_id, message, level="info", lead_id=None, lead_data=None):
        self.register_job(job_id)
        
        payload = {
            "level": level,
            "message": message
        }
        
        if lead_id: payload["lead_id"] = lead_id
        if lead_data: payload["lead_data"] = lead_data
        
        msg_str = json.dumps(payload)
        self.job_history[job_id].append(msg_str)
        
        for q in self.job_queues[job_id]:
            q.put(msg_str)

    def remove_queue(self, job_id, q):
        if job_id in self.job_queues and q in self.job_queues[job_id]:
            self.job_queues[job_id].remove(q)

job_logger = JobLogger()
