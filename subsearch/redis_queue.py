"""
Redis-based queue management for Sub Search

This module provides a robust, persistent queue system using Redis that replaces
the in-memory queue with proper prioritization and persistence.

Features:
- Priority queue (manual searches before automated)
- Queue persistence across restarts
- Job state tracking
- ETA calculations
- Queue monitoring and metrics
"""

import json
import time
import redis
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timezone
from dataclasses import dataclass, asdict


@dataclass
class QueuedJob:
    """Represents a job in the queue."""
    job_id: str
    priority: int  # 0 = manual (high), 1 = automated (low)
    keyword: Optional[str]
    limit: int
    source: str
    enqueued_at: float  # Unix timestamp
    # Additional job config stored as JSON string
    job_config: str


class RedisQueue:
    """Redis-based priority queue for job management."""

    # Redis key prefixes
    QUEUE_KEY = "subsearch:queue"  # Sorted set for priority queue
    JOB_PREFIX = "subsearch:job:"  # Hash for job details
    RUNNING_SET = "subsearch:running"  # Set of running job IDs
    STATS_KEY = "subsearch:stats"  # Hash for queue statistics

    def __init__(self, redis_url: str = "redis://localhost:6379/0"):
        """Initialize Redis queue.

        Args:
            redis_url: Redis connection URL (default: redis://localhost:6379/0)
        """
        self.redis = redis.from_url(redis_url, decode_responses=True)

    def enqueue(self, job_id: str, priority: int, job_data: Dict) -> None:
        """Add a job to the queue with priority.

        Args:
            job_id: Unique job identifier
            priority: Priority level (0=high, 1=low)
            job_data: Job configuration and metadata
        """
        # Store job details
        job_key = f"{self.JOB_PREFIX}{job_id}"
        job_info = QueuedJob(
            job_id=job_id,
            priority=priority,
            keyword=job_data.get("keyword"),
            limit=job_data.get("limit", 1000),
            source=job_data.get("source", "sub_search"),
            enqueued_at=time.time(),
            job_config=json.dumps(job_data)
        )

        # Store job data in Redis hash
        self.redis.hset(job_key, mapping=asdict(job_info))

        # Add to priority queue (sorted set)
        # Score = priority * 1e12 + enqueued_at (ensures FIFO within priority)
        score = priority * 1e12 + job_info.enqueued_at
        self.redis.zadd(self.QUEUE_KEY, {job_id: score})

        # Update stats
        self.redis.hincrby(self.STATS_KEY, "total_enqueued", 1)

    def dequeue(self) -> Optional[str]:
        """Remove and return the highest priority job from the queue.

        Returns:
            Job ID if available, None if queue is empty
        """
        # Get the job with the lowest score (highest priority)
        result = self.redis.zpopmin(self.QUEUE_KEY, count=1)

        if not result:
            return None

        job_id, score = result[0]

        # Add to running set
        self.redis.sadd(self.RUNNING_SET, job_id)

        # Update stats
        self.redis.hincrby(self.STATS_KEY, "total_dequeued", 1)

        return job_id

    def mark_complete(self, job_id: str) -> None:
        """Mark a job as complete and remove from running set.

        Args:
            job_id: Job identifier
        """
        # Remove from running set
        self.redis.srem(self.RUNNING_SET, job_id)

        # Optionally cleanup job data (or keep for history)
        # self.redis.delete(f"{self.JOB_PREFIX}{job_id}")

        # Update stats
        self.redis.hincrby(self.STATS_KEY, "total_completed", 1)

    def mark_failed(self, job_id: str) -> None:
        """Mark a job as failed and remove from running set.

        Args:
            job_id: Job identifier
        """
        # Remove from running set
        self.redis.srem(self.RUNNING_SET, job_id)

        # Update stats
        self.redis.hincrby(self.STATS_KEY, "total_failed", 1)

    def remove_from_queue(self, job_id: str) -> bool:
        """Remove a specific job from the queue (e.g., user cancellation).

        Args:
            job_id: Job identifier

        Returns:
            True if job was removed, False if not found
        """
        removed = self.redis.zrem(self.QUEUE_KEY, job_id)
        if removed:
            # Cleanup job data
            self.redis.delete(f"{self.JOB_PREFIX}{job_id}")
            return True
        return False

    def get_job_data(self, job_id: str) -> Optional[Dict]:
        """Get job data from Redis.

        Args:
            job_id: Job identifier

        Returns:
            Job data dictionary or None if not found
        """
        job_key = f"{self.JOB_PREFIX}{job_id}"
        data = self.redis.hgetall(job_key)

        if not data:
            return None

        # Parse job_config JSON
        if "job_config" in data:
            data["job_config"] = json.loads(data["job_config"])

        # Convert numeric fields
        data["priority"] = int(data.get("priority", 0))
        data["limit"] = int(data.get("limit", 1000))
        data["enqueued_at"] = float(data.get("enqueued_at", 0))

        return data

    def get_queue_status(self, limit: int = 10) -> List[Dict]:
        """Get current queue status with ETA calculations.

        Args:
            limit: Maximum number of queue items to return

        Returns:
            List of queue items with position and ETA info
        """
        # Get jobs in priority order
        queue_items = self.redis.zrange(self.QUEUE_KEY, 0, limit - 1, withscores=True)

        # Calculate average job time (simple estimate - could be improved)
        avg_job_time = self._get_average_job_time()

        results = []
        for idx, (job_id, score) in enumerate(queue_items):
            job_data = self.get_job_data(job_id)
            if not job_data:
                continue

            eta_start = int(idx * avg_job_time)
            eta_completion = int((idx + 1) * avg_job_time)

            results.append({
                "job_id": job_id,
                "keyword": job_data.get("keyword") or "All subreddits",
                "limit": job_data["limit"],
                "source": job_data["source"],
                "priority": job_data["priority"],
                "position": idx + 1,
                "eta_start_seconds": eta_start,
                "eta_completion_seconds": eta_completion,
                "is_manual": job_data["priority"] == 0,
            })

        return results

    def get_queue_size(self) -> int:
        """Get total number of jobs in queue."""
        return self.redis.zcard(self.QUEUE_KEY)

    def get_running_count(self) -> int:
        """Get number of currently running jobs."""
        return self.redis.scard(self.RUNNING_SET)

    def get_running_jobs(self) -> List[str]:
        """Get list of currently running job IDs."""
        return list(self.redis.smembers(self.RUNNING_SET))

    def is_running(self, job_id: str) -> bool:
        """Check if a job is currently running."""
        return self.redis.sismember(self.RUNNING_SET, job_id)

    def is_queued(self, job_id: str) -> bool:
        """Check if a job is in the queue."""
        return self.redis.zscore(self.QUEUE_KEY, job_id) is not None

    def get_queue_position(self, job_id: str) -> Optional[int]:
        """Get the position of a job in the queue.

        Args:
            job_id: Job identifier

        Returns:
            Position (1-indexed) or None if not in queue
        """
        rank = self.redis.zrank(self.QUEUE_KEY, job_id)
        if rank is None:
            return None
        return rank + 1  # Convert to 1-indexed

    def get_stats(self) -> Dict:
        """Get queue statistics.

        Returns:
            Dictionary with queue metrics
        """
        stats = self.redis.hgetall(self.STATS_KEY)

        return {
            "total_enqueued": int(stats.get("total_enqueued", 0)),
            "total_dequeued": int(stats.get("total_dequeued", 0)),
            "total_completed": int(stats.get("total_completed", 0)),
            "total_failed": int(stats.get("total_failed", 0)),
            "current_queue_size": self.get_queue_size(),
            "current_running": self.get_running_count(),
        }

    def _get_average_job_time(self) -> float:
        """Get average job execution time in seconds.

        This is a simple estimate. In production, you'd want to track
        actual job completion times and calculate a rolling average.

        Returns:
            Average job time in seconds (default: 60)
        """
        # Could be improved by tracking actual completion times
        return 60.0

    def clear_all(self) -> None:
        """Clear all queue data. USE WITH CAUTION!"""
        # Get all job IDs from queue
        job_ids = self.redis.zrange(self.QUEUE_KEY, 0, -1)

        # Delete job data
        for job_id in job_ids:
            self.redis.delete(f"{self.JOB_PREFIX}{job_id}")

        # Clear queue and running set
        self.redis.delete(self.QUEUE_KEY)
        self.redis.delete(self.RUNNING_SET)
        self.redis.delete(self.STATS_KEY)

    def health_check(self) -> bool:
        """Check if Redis connection is healthy.

        Returns:
            True if Redis is reachable, False otherwise
        """
        try:
            self.redis.ping()
            return True
        except Exception:
            return False
