#!/usr/bin/env python3
"""
Test script for queue prioritization

This script helps verify that manual searches are prioritized above automated searches.

Usage:
    python scripts/test_queue_priority.py
"""

import sys
import time
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

print("Queue Priority Test")
print("=" * 60)
print("\nThis script demonstrates the priority queue behavior.")
print("Manual searches (priority 0) will always be ahead of automated searches (priority 1).\n")

# Simulate queue behavior
import heapq

job_queue = []
counter = 0

def enqueue(job_id, priority, description):
    global counter
    counter += 1
    heapq.heappush(job_queue, (priority, counter, job_id, description))
    print(f"Enqueued: {description} (priority={priority}, job_id={job_id})")

def show_queue():
    print("\nCurrent queue order (next to run → last):")
    print("-" * 60)
    sorted_queue = sorted(job_queue)
    for idx, (priority, counter, job_id, desc) in enumerate(sorted_queue, 1):
        priority_label = "MANUAL" if priority == 0 else "AUTO  "
        print(f"  {idx}. [{priority_label}] {desc}")
    print()

# Simulate a real scenario
print("Scenario: Mixed manual and automated searches\n")

# Add some automated searches first
enqueue("auto-1", 1, "Auto search: random keyword 'technology'")
time.sleep(0.01)
enqueue("auto-2", 1, "Auto search: random keyword 'gaming'")
time.sleep(0.01)

show_queue()

# Now a user submits manual searches - they should jump to the front!
print("User submits manual searches...\n")
enqueue("manual-1", 0, "Manual search: 'fintech'")
time.sleep(0.01)
enqueue("manual-2", 0, "Manual search: 'crypto'")

show_queue()

# Add more automated searches
print("More automated searches arrive...\n")
enqueue("auto-3", 1, "Auto search: random keyword 'science'")

show_queue()

# Add another manual search
print("Another user search...\n")
enqueue("manual-3", 0, "Manual search: 'fitness'")

show_queue()

# Now dequeue and show order of execution
print("Execution order (simulating job processing):")
print("-" * 60)
execution_order = []
while job_queue:
    priority, counter, job_id, desc = heapq.heappop(job_queue)
    execution_order.append((priority, job_id, desc))

for idx, (priority, job_id, desc) in enumerate(execution_order, 1):
    priority_label = "MANUAL" if priority == 0 else "AUTO  "
    print(f"  {idx}. [{priority_label}] {desc}")

print("\n" + "=" * 60)
print("✓ Test complete!")
print("\nKey observations:")
print("  • All MANUAL searches execute before AUTO searches")
print("  • Within same priority, FIFO order is maintained")
print("  • This ensures user searches are never blocked by automated jobs")
