from graphviz import Digraph
from stmlearn.suls import MealyMachine, DFA

import itertools
def _render(fsm: MealyMachine, filename):
    states = sorted(fsm.get_states(), key=lambda x: int(x.name.strip('s')))
    alphabet = sorted(fsm.get_alphabet())

    g = Digraph('G', filename=filename)
    g.attr(rankdir='LR')

    # Add states
    for state in states:
        g.node(state.name)

    # Add transitions:
    for state in states:
        for action, (other_state, output) in sorted(state.edges.items(), key=lambda x: x[0]):
            g.edge(state.name, other_state.name, label=f'{action}/{output}')

    g.save()


def check_distinguishing_set(fsm, dset):
    outputs = get_dset_outputs(fsm, dset)

    if len(set(outputs.values())) < len(outputs):
        print("Dset outputs not unique!")
        print('Dset size:', len(dset))
        print("Dset: ", dset)
        # print("Outputs:", list(outputs.values()))
        # print("Outputs", outputs)
        for (ka, va), (kb, vb) in itertools.product(outputs.items(), outputs.items()):
            if ka != kb and va == vb:
                print(va, vb)
                ma = MealyMachine(initial_state=ka)
                mb = MealyMachine(initial_state=kb)
                render_options = {'ignore_edges': ['invalid_input']}
                ma.render_graph(filename='/tmp/out/ma.pdf', render_options=render_options)
                mb.render_graph(filename='/tmp/out/mb.pdf', render_options=render_options)
                print('names', ka.name, kb.name)
        
        input("NOT MINIMAL, enter to continue")
        return True
        # return False
    else:
        print('Dset succes!', len(outputs), 'states,', len(set(outputs)), 'unique outputs')
        print('Dset size:', len(dset))
        return True


def get_dset_outputs(fsm, dset):
    states = fsm.get_states()
    outputs = {}
    for state in states:
        if isinstance(fsm, MealyMachine):
            mm = MealyMachine(state)
        elif isinstance(fsm, DFA):
            mm = DFA(state, fsm.accepting_states)

        out = []
        for dseq in dset:
            out.append(mm.process_input(dseq))
            mm.reset()
        outputs[state] = tuple(out.copy())
    return outputs


