import tempfile

from stmlearn.suls import MealyMachine, MealyState
from itertools import product, chain, combinations
from functools import reduce
from stmlearn.learners import Learner
from stmlearn.teachers import Teacher
from typing import Set, Tuple, Dict, Callable, Iterable
from tabulate import tabulate
from stmlearn.util import NotifierSet
from collections import namedtuple
from pathlib import Path
import random
import string
from datetime import datetime
import pickle

ChangeCounterPair = namedtuple('Mem', 'S E')

# Memoization decorator
def depends_on_S(func):
    def wrapper(*args):

        self = args[0]
        change_counter = self.S.change_counter

        try:
            last_seen = self._watch[func.__name__]
        except KeyError:
            self._watch[func.__name__] = 0
            last_seen = 0

        if last_seen != change_counter:
            tmp = func(*args)
            self._mem[func.__name__] = tmp
            self._watch[func.__name__] = change_counter
            return tmp
        else:
            return self._mem[func.__name__]

    return wrapper

# Memoization decorator
def depends_on_S_E(func):
    def wrapper(*args):

        self = args[0]
        change_counter_S = self.S.change_counter
        change_counter_E = self.E.change_counter

        try:
            last_seen_S, last_seen_E = self._watch[func.__name__]
        except KeyError:
            self._watch[func.__name__] = ChangeCounterPair(-1, -1)
            last_seen_S, last_seen_E = -1, -1

        if (last_seen_S != change_counter_S) or (last_seen_E != change_counter_E):
            # If S or E changed, Invalidate memory
            self._mem[func.__name__] = {}
            self._watch[func.__name__] = ChangeCounterPair(change_counter_S, change_counter_E)

        if args in self._mem[func.__name__].keys():
            return self._mem[func.__name__][args]
        else:
            tmp = func(*args)
            self._mem[func.__name__][args] = tmp
            return tmp

    return wrapper


# Generic memoization decorator
def memoize(f):
    memo = {}

    def wrapper(*args):
        if args not in memo:
            memo[args] = f(*args)
        return memo[args]

    return wrapper


# Implements the L* algorithm by Dana Angluin, modified for mealy machines as per
# https://link.springer.com/chapter/10.1007%2F978-3-642-05089-3_14
class LStarMealyLearner(Learner):
    def __init__(self, teacher: Teacher):
        super().__init__(teacher)

        # Observation table (S, E, T)
        # NotifierSets raise a flag once they're modified
        # This is used to avoid repeating expensive computations
        self.S = NotifierSet()
        self.E = NotifierSet()

        # S starts with the empty string
        self.S.add(tuple())

        self.T = {}

        # Alphabet A
        self.A = set([(x,) for x in teacher.get_alphabet()])

        # at the start, E = A
        for a in self.A:
            self.E.add(a)


        # Don't redo expensive computations unless necessary
        self._mem = {}
        self._watch = {}

        # Checkpoints?
        self._save_checkpoints = False
        self._checkpointname = None
        self._checkpointdir = None

    def enable_checkpoints(self, dir, checkpointname=None):
        # Try getting checkpoint name from SUL
        if checkpointname is None:
            try:
                cpn = Path(self.teacher.sul.path).stem
            except:
                cpn = ''.join([random.choice(string.ascii_letters + string.digits) for n in range(6)])
        else:
            cpn = checkpointname

        self._checkpointname = cpn
        self._save_checkpoints = True

        # Check if checkpoint dir exists
        Path(f'{dir}/{cpn}').mkdir(parents=True, exist_ok=True)
        self._checkpointdir = dir

        return self

    def make_checkpoint(self):
        state = {
            "S": self.S,
            "E": self.E,
            "T": self.T
        }

        print("Making checkpoint...")
        now = str(datetime.now()).replace(' ', '_').replace('.', ':')
        with open(Path(self._checkpointdir).joinpath(self._checkpointname + '/' + now), 'wb') as f:
            pickle.dump(state, f)

    def load_checkpoint(self, path):
        with open(path, 'rb') as f:
            state = pickle.load(f)
            for k, v in state.items():
                self.__dict__[k] = v
        return self

    # Membership query
    def query(self, query) -> str | None:
        return self.teacher.member_query(query)
        if query in self.T.keys():
            return self.T[query]
        else:
            output = self.teacher.member_query(query)
            self.T[query] = output
            return output

    # Calculates S·A
    @depends_on_S
    def _SA(self):
        return set([tuple(chain.from_iterable(x)) for x in list(product(self.S, self.A))]).union(self.A)

    # Calculates S ∪ S·A
    @depends_on_S
    def _SUSA(self) -> Set[Tuple]:
        SA = self._SA()

        #print('S·A', SA)

        return self.S.union(SA)

    def _tostr(self, actionlist):
        if len(actionlist) == 0:
            return 'λ'
        else:
            return reduce(lambda x, y: str(x) + ',' + str(y), actionlist)

    @memoize
    def _rebuildquery(self, strquery):
        return tuple(filter(lambda x: x != 'λ', strquery.split(',')))

    # row(s), s in S ∪ S·A
    @depends_on_S_E
    def _get_row(self, s: Tuple) -> list[str | None]:
        if s not in self._SUSA():
            raise Exception("s not in S ∪ S·A")

        row = [self.query(s + e) for e in self.E]

        return row

    def _get_col(self, e: Tuple):
        if e not in self.E:
            raise Exception("e not in E")

        col = [self.query(s + e) for s in self._SUSA()]

        return col

    @depends_on_S_E
    def _is_closed(self):
        is_closed = True

        S_rows = [self._get_row(s) for s in self.S]

        for t in self._SA():
            is_closed &= self._get_row(t) in S_rows

        return is_closed

    @depends_on_S_E
    def _is_consistent(self):
        is_consistent = True

        # Gather equal rows
        eqrows = [(s1, s2) for (s1, s2) in combinations(self.S, 2) if self._get_row(s1) == self._get_row(s2)]

        # Check if all these rows are still consistent after appending a
        for (s1, s2) in eqrows:
            for a in self.A:
                cur_consistent = self._get_row(s1 + a) == self._get_row(s2 + a)
                # if not cur_consistent:
                # print("Inconsistency found:", f'{s1},{a}', f'{s2},{a}')
                is_consistent &= cur_consistent

        return is_consistent

    def print_observationtable(self):

        rows = []

        # S = sorted([self._tostr(a) for a in list(self.S)])
        # SA = sorted([self._tostr(a) for a in list(self._SA())])
        # E = sorted([self._tostr(e) for e in self.E]) if len(self.E) > 0 else []

        rows.append([" ", "T"] + list(map(str, self.E)))
        for s in self.S:
            row = ["S", str(s)]
            # for e in E:
            #     row.append(self._get_row(self._rebuildquery(f'{s},{e}')))
            row.extend(map(str, self._get_row(s)))
            rows.append(row)

        rows_sa = []
        for sa in self._SA():
            row = ["SA", str(sa)]
            # for e in E:
            #     row.append(self.query(self._rebuildquery(f'{sa},{e}')))
            row.extend(map(str, self._get_row(sa)))
            rows_sa.append(row)

        print(tabulate(rows + rows_sa, headers="firstrow",tablefmt="fancy_grid"))

    def step(self):
        consistent = self._is_consistent()
        closed = self._is_closed()

        print('Closed:', closed)
        print('Consistent:', consistent)

        break_consistent = False

        if not consistent:
            # Gather equal rows
            eqrows = [(s1, s2) for (s1, s2) in combinations(self.S, 2) if self._get_row(s1) == self._get_row(s2)]

            # Check if T(s1·a·e) != T(s2·a·e), and add a·e to E if so.
            AE = list(product(self.A, self.E))
            for (s1, s2) in eqrows:
                for (a, e) in AE:
                    T_s1ae = self.query(s1 + a + e)
                    T_s2ae = self.query(s2 + a + e)

                    if T_s1ae != T_s2ae:
                        print('Adding', self._tostr(a + e), 'to E')
                        self.E.add(a + e)
                        break_consistent = True
                        break

                if break_consistent:
                    break

            # Rebuild observation table
            #self.print_observationtable()

        if not closed:
            # Gather all rows in S
            S_rows = [self._get_row(s) for s in self.S]

            # Find a row(s·a) that is not in [row(s) for all s in S]
            SA = product(self.S, self.A)
            for (s, a) in SA:
                row_sa = self._get_row(s + a)
                if row_sa not in S_rows:
                    self.S.add(s + a)
                    #break




    # Builds the hypothesised dfa using the currently available information
    def build_dfa(self):
        # Gather states from S
        S = self.S

        # The rows can function as index to the 'state' objects
        state_rows = set([tuple(self._get_row(s)) for s in S])
        initial_state_row = tuple(self._get_row(tuple()))


        # Generate state names for convenience
        state_names = {state_row: f's{n + 1}' for (n, state_row) in enumerate(state_rows)}

        # Build the state objects and get the initial and accepting states
        states: Dict[Tuple, MealyState] = {state_row: MealyState(state_names[state_row]) for state_row in state_rows}
        initial_state = states[initial_state_row]

        # Add the connections between states
        A = [a for (a,) in self.A]
        # Keep track of states already visited
        visited_rows = []
        for s in S:
            s_row = tuple(self._get_row(s))
            if s_row not in visited_rows:
                for a in A:
                    sa_row = tuple(self._get_row(s + (a,)))
                    if sa_row in states.keys():
                        try:
                            cur_output = self.query(s + (a,))
                            states[s_row].add_edge(a, cur_output, states[sa_row])
                        except:
                            # Can't add the same edge twice
                            pass
            else:
                visited_rows.append(s_row)

        return MealyMachine(initial_state)

    def run(self, show_intermediate=False, print_observationtable=False, render_options=None, on_hypothesis: Callable[[MealyMachine], None] = None) -> MealyMachine:
        equivalent = False

        if print_observationtable:
            print("Initial observation table:")
            self.print_observationtable()

        while not equivalent:
            while not (self._is_closed() and self._is_consistent()):
                if print_observationtable:
                    self.print_observationtable()
                self.step()

            if self._save_checkpoints:
                self.make_checkpoint()

            # Are we equivalent?
            hypothesis = self.build_dfa()
            print("HYPOTHESIS")
            print(hypothesis)

            if show_intermediate:
                hypothesis.render_graph(render_options=render_options)

            if on_hypothesis is not None:
                on_hypothesis(hypothesis)

            equivalent, counterexample = self.teacher.equivalence_query(hypothesis)

            if equivalent:
                return hypothesis

            print('COUNTEREXAMPLE', counterexample)
            hypothesis.reset()
            print('Hypothesis output:', hypothesis.process_input(counterexample))
            print('SUL output:', self.query(counterexample))

            print()

            # if not, add counterexample and prefixes to S
            for i in range(1, len(counterexample) + 1):
                self.S.add(counterexample[0:i])