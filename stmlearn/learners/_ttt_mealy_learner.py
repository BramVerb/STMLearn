from stmlearn.suls import MealyMachine, MealyState as State
from stmlearn.teachers import Teacher
from ..learners._ttt_abstract_learner import TTTAbstractLearner


# Implements the TTT algorithm
class TTTMealyLearner(TTTAbstractLearner):
    def __init__(self, teacher: Teacher):
        # Access sequences S + state bookkeeping
        self.S = {tuple(): State("s0")}

        super().__init__(teacher)

    def sift(self, sequence):
        cur_dtree_node = self.DTree.root
        prev_dtree_node = None

        response: str|None = None
        while not cur_dtree_node is None and not cur_dtree_node.isLeaf:
            # Figure out which branch we should follow
            seq = sequence + cur_dtree_node.suffix
            response = self.query(seq)
            prev_dtree_node = cur_dtree_node
            if response in cur_dtree_node.children:
                cur_dtree_node = cur_dtree_node.children[response]
            else:
                cur_dtree_node = None

        # If we end up on an empty node, we can add a new leaf pointing to the
        # state accessed by the given sequence
        if cur_dtree_node is None:
            new_acc_seq = sequence
            assert new_acc_seq not in self.S
            print("Created new state:", f's{len(self.S)}')
            new_state = State(f's{len(self.S)}')
            new_dtree_node = self.DTree.createLeaf(new_state)
            self.S[new_acc_seq] = new_state
            assert response is not None
            assert prev_dtree_node is not None
            prev_dtree_node.add(response, new_dtree_node)
            cur_dtree_node = new_dtree_node

        assert cur_dtree_node is not None, "Oof this shouldn't happen"
        assert cur_dtree_node.isLeaf, "This should always be a leaf node"
        assert cur_dtree_node.state is not None, "Leaf nodes should always represent a state"

        return cur_dtree_node.state


    def construct_hypothesis(self):
        # Keep track of the initial state
        initial_state = self.S[()]

        # Keep track of the amount of states, so we can sift again if
        # the sifting process created a new state
        n = len(list(self.S.items()))
        items_added = True

        # Todo: figure out a neater way to handle missing states during sifting than to just redo the whole thing
        while items_added:
            # Add transitions
            for access_seq, cur_state in list(self.S.items()):
                for a in self.A:
                    next_state = self.sift(access_seq + a)
                    output = self.query(access_seq + a)
                    cur_state.add_edge(a[0], output, next_state, override=True)

            # Check if no new state was added
            n2 = len((self.S.items()))

            items_added = n != n2
            # print("items added", items_added)

            n = n2

        # Add spanning tree transitions
        for access_seq, state in self.S.items():
            if len(access_seq) > 0:
                ancestor_acc_seq = access_seq[0:-1]
                ancestor_state = self.S[ancestor_acc_seq]
                a = access_seq[-1]
                output = self.query(ancestor_acc_seq + (a,))
                ancestor_state.add_edge(a, output, state, override=True)

        # Find accepting states
        # accepting_states = [state for access_seq, state in self.S.items() if self.query(access_seq)]

        return MealyMachine(initial_state)

    def process_counterexample(self, counterexample):
        u, a, v = self.decompose(counterexample)

        # This state q_old needs to be split:
        q_old_state = self.get_state_from_sequence(u + a)
        q_old_acc_seq = self.get_access_sequence_from_state(q_old_state)

        # Store new state and access sequence
        q_new_acc_seq = self.get_access_sequence(u) + a
        # if q_new_acc_seq in self.S:
        #     q_new_state = self.S[q_new_acc_seq]
        # else:
        q_new_state = State(f's{len(self.S)}')

        assert q_new_acc_seq not in self.S

        self.S[q_new_acc_seq] = q_new_state

        ### update the DTree:
        # find the leaf corresponding to the state q_old
        q_old_leaf = self.DTree.getLeaf(q_old_state)
        # and create a new inner node,
        new_inner = self.DTree.createInner(v, temporary=True)

        # replace the old leaf node with the new inner node
        q_old_leaf.replace(new_inner)

        # check what branch the children should go
        response_q_old = self.query(q_old_acc_seq + v)
        response_q_new = self.query(q_new_acc_seq + v)
        # response_q_old = self.query(u + v)
        # response_q_new = self.query(q_new_acc_seq + v)
        assert response_q_new != response_q_old, "uh oh this should never happen"

        # prepare leaf node for the new state
        q_new_leaf = self.DTree.createLeaf(q_new_state)

        # Add the children to the corresponding branch of the new inner node
        new_inner.add(response_q_new, q_new_leaf)
        new_inner.add(response_q_old, q_old_leaf)

        print("split:", q_old_state.name, q_new_state.name)
        #
        # if response_q_new == True:
        #     new_inner.addTrue(q_new_leaf)
        #     new_inner.addFalse(q_old_leaf)
        # else:
        #     new_inner.addTrue(q_old_leaf)
        #     new_inner.addFalse(q_new_leaf)
