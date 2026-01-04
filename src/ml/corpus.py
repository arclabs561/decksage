import csv
import random
from itertools import islice


class CollectionsCorpus:
    def __init__(self, path, limit=None):
        self.path = path
        self.limit = limit

    def __iter__(self):
        with open(self.path) as f:
            for record in islice(csv.reader(f), self.limit):
                random.shuffle(record)
                yield record
