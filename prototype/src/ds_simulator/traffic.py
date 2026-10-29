"""Bounded traffic history and display aggregation, independent of Qt."""
from collections import Counter, deque
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
import math
import time

MAX_RECORDS = 2000


@dataclass(frozen=True)
class TrafficSnapshot:
    records: tuple
    totals: dict
    last_rx: dict
    rates: dict
    captured_at: float
    received: int

    def stats(self, connection_id=None):
        totals = {direction: sum(count for (identifier, kind), count in self.totals.items() if kind == direction and (connection_id is None or identifier == connection_id)) for direction in ('TX', 'RX')}
        times = [stamp for identifier, stamp in self.last_rx.items() if connection_id is None or identifier == connection_id]
        totals['last_rx'] = max(times) if times else None
        return totals

    def rate_series(self, end, count=20, connection_id=None):
        result = []
        for second in range(math.floor(end) - count + 1, math.floor(end) + 1):
            bucket = self.rates.get(second, {})
            totals = {direction: sum(value for (identifier, kind), value in bucket.items() if kind == direction and (connection_id is None or identifier == connection_id)) for direction in ('TX', 'RX')}
            result.append((second, totals['TX'], totals['RX']))
        return result


class TrafficHistory:
    def __init__(self):
        self.records = deque(maxlen=MAX_RECORDS)
        self.totals = Counter()
        self.last_rx = {}
        self.rates = {}
        self.received = 0

    def append(self, event):
        record = deepcopy(event)
        if record.get('direction') not in ('TX', 'RX'):
            raise ValueError('Traffic direction must be TX or RX')
        stamp = datetime.fromisoformat(record['time']).timestamp()
        if not math.isfinite(stamp):
            raise ValueError('Invalid event time')
        identifier, direction = record['connection_id'], record['direction']
        self.received += 1
        record['event_id'], record['_timestamp'] = self.received, stamp
        self.records.append(record)
        self.totals[identifier, direction] += 1
        if direction == 'RX':
            self.last_rx[identifier] = max(stamp, self.last_rx.get(identifier, stamp))
        self.rates.setdefault(math.floor(stamp), Counter())[identifier, direction] += 1
        # Rates remain correct even after individual records leave the display buffer.
        if len(self.rates) > 120:
            for second in sorted(self.rates)[:-120]:
                del self.rates[second]
        return record

    def snapshot(self, now=None):
        return TrafficSnapshot(tuple(self.records), dict(self.totals), dict(self.last_rx), {second: dict(bucket) for second, bucket in self.rates.items()}, time.time() if now is None else now, self.received)


def lane_key(record):
    if record.get('connection_mode') == 'TCP Server':
        return record['connection_id'], record['socket_id']
    return record['connection_id'], ''


def display_groups(records, start, end, slots, connection_id=None):
    """Bucket overlapping events. Never infer request/response relationships."""
    slots = max(1, slots)
    span = max(end - start, .001)
    groups = {}
    for record in records:
        stamp = record['_timestamp']
        if not start <= stamp <= end or (connection_id is not None and record['connection_id'] != connection_id):
            continue
        # A spectrum burst is represented by its one-second bucket, not 250 boxes.
        display_time = math.floor(stamp) + .5 if record['message'] == 'SPECTRUM_DATA' else stamp
        slot = min(slots - 1, max(0, math.floor((display_time - start) / span * slots)))
        key = lane_key(record), record['direction'], slot
        groups.setdefault(key, []).append(record)
    return [(key, tuple(sorted(values, key=lambda r: (r['_timestamp'], r['event_id'])))) for key, values in sorted(groups.items())]
