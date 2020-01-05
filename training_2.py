# Performs a training of the current MNN model
# TODO: store the generated graphs and data to make sure the experiments are replicable
# TODO: store results of experiments in a file

import dgl
from generate_dataset_2 import DatasetGenerator
import torch
import torch.nn as nn
from mpnn_2 import MPNN
import time
import networkx as nx
from matplotlib import pyplot as plt
import numpy as np

# Setting the seed for replicability
import random
random.seed(33)

use_cuda = torch.cuda.is_available()

#####################################################
# --- Training parameters
#####################################################

# For the training hyperparameters, insire from paper
nb_epochs = 50
nb_features = 32
lr = 0.005

# Datasets parameters
graph_type = 'erdos_renyi'
nb_graphs = 5
nb_nodes = 5
algorithm_type = 'DFS'

max_steps = nb_nodes + 1 # maximum number of steps before stopping
# I added +1 as experimentally the case happends, to investigate

####################################################
# --- Data generation
####################################################

start = time.time()
data_gen = DatasetGenerator()
graphs, next_nodes = data_gen.run(graph_type, nb_graphs, nb_nodes,
                                algorithm_type)

print('Dataset created in:', time.time()-start)
clock = time.time()

import pdb; pdb.set_trace()

# Prepare the data in an easily exploitable format
# It could probably be optimised with DGL

terminations = []
edges_mats = []
next_nodes = list(next_nodes)
# next_nodes = np.asarray(next_nodes)
# Do all the necessary transforms on the data
for i in range(nb_graphs):
    states = np.asarray(next_nodes[i])
    # termination = np.zeros(states.shape[0])
    termination = np.zeros(len(states))
    termination[-1] = 1
    
    # Adding self edge to every node, as in the paper
    for j in range(nb_nodes):
        graphs[i].add_edge(j, j)

    assert max_steps >= len(states)

    # set states to fixed lenght with termination boolean to be able to compute termination error
    # if states.shape[0] < max_steps:
    #     pad_idx = [(0,0) for i in range(states.ndim)]
    #     pad_idx[0] = (0, max_steps-states.shape[0])
    #     state = np.pad(states, pad_idx, 'edge')
    #     termination = np.pad(termination, (0, max_steps-termination.size), 'constant', constant_values=(1))
    
    # next_nodes[i] = state
    # For nn.CrossEntroppyLoss, next node is expected to be an index and not 1 hot
    # nextnode_data = np.argmax(nextnode_data, axis=1)
    terminations.append(termination)
    edges_mats.append(nx.to_numpy_matrix(graphs[i]))
    g = dgl.DGLGraph()
    g.from_networkx(graphs[i], node_attrs=['priority'])
    graphs[i] = g

# Take 10% of the graphs as validation
nb_val = int(0.1*nb_graphs)

train_data = [(graphs[i], edges_mats[i], next_nodes[i], terminations[i]) for i in range(nb_graphs-nb_val)]
test_data = [(graphs[i], edges_mats[i], next_nodes[i], terminations[i]) for i in range(nb_graphs-nb_val, nb_graphs)]

###################################################

model = MPNN(1, 32, 1, 1, useCuda=use_cuda)
optimizer = torch.optim.Adam(model.parameters(), lr=lr)

if use_cuda:
    print('Using GPU')
    model.cuda()
else:
    print('Using CPU')

model.train()

def nll_gaussian(preds, target):
    neg_log_p = ((preds - target) ** 2)
    return neg_log_p.sum() / (target.size(0) * target.size(1))

verbose = False

teacher_forcing = True

if teacher_forcing:
    print('Using teacher forcing!')

for epoch in range(nb_epochs):
    print('Epoch:', epoch)

    losses = []
    clock = time.time()

    for batch_idx, (graph, edges_mat, states, termination) in enumerate(train_data):

        states = torch.from_numpy(np.asarray(states))
        edges_mat = torch.from_numpy(edges_mat)
        termination = torch.from_numpy(termination)
        
        import pdb; pdb.set_trace()

        if use_cuda:
            states, edges_mat, termination = states.cuda(), edges_mat.cuda(), termination.cuda()

        if verbose:
                print('--- Processing new graph! ---')
                print('edges_mat shape:', edges_mat.shape)
                print('states shape (after reshape):', states.shape)
                print('termination shape (after reshape):', termination.shape)

        # We do optimizer call only after completely processing the graph
        preds, pred_stops = model(graph, states, edges_mat)

        # Compare the components of the loss for tuning
                
        # target = [np.where(states[0])[0]]
        target = []
        target.extend([np.where(states[i]-states[i-1])[0] for i in range(1, states.shape[0])])
        target = np.hstack(target)
        target = torch.LongTensor(target)

        loss = nn.CrossEntropyLoss()
        output = loss(preds, target)
        print(output.item())
        
        loss2 = nn.BCELoss()
        output += loss2(pred_stops.view(-1, 1), termination.float().view(-1, 1))

        optimizer.zero_grad()
        output.backward()
        optimizer.step()

        losses.append(output.item())

    print('Epoch run in:', time.time()-clock)
    clock = time.time()
    print('Loss:', np.mean(np.asarray(losses)))

import pdb; pdb.set_trace()
print('states:', states)
print('pred:', preds)
print('termination:', termination)
print('pred_stops:', pred_stops)