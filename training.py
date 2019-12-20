# Performs a training of the current MNN model
# TODO: store the generated graphs and data to make sure the experiments are replicable
# TODO: store results of experiments in a file

import dgl
from generate_dataset import DatasetGenerator
import torch
import torch.nn as nn
from mpnn import MPNN
import time
import networkx as nx
import numpy as np

# Setting the seed for replicability
import random
random.seed(33)

use_cuda = torch.cuda.is_available()

#####################################################
# --- Training parameters
#####################################################

# For the training hyperparameters, insire from paper
nb_epochs = 10
nb_features = 32
lr = 0.01

# Datasets parameters
graph_type = 'erdos_renyi'
nb_graphs = 200
nb_nodes = 20
algorithm_type = 'DFS'

max_steps = nb_nodes + 1 # maximum number of steps before stopping
# I added +1 as experimentally the case happends, to investigate

####################################################
# --- Data generation
####################################################

start = time.time()
data_gen = DatasetGenerator()
graphs, history_dataset = data_gen.run(graph_type, nb_graphs, nb_nodes,
                                algorithm_type)

#print(history_dataset[:5])

#print(history_dataset[5000])

print('Dataset created in:', time.time()-start)
clock = time.time()

# Inspect some shapes
for i in range(10):
    pass
    #print(history_dataset[i].shape)

# Prepare the data in an easily exploitable format
# It could probably be optimised with DGL

terminations = []
edges_mats = []

# Do all the necessary transforms on the data
for i in range(nb_graphs):
    states = history_dataset[i]
    termination = np.zeros(states.shape[0])
    termination[-1] = 1
    # Adding self edge to every node, as in the paper
    '''for j in range(nb_nodes):
        graphs[i].add_edge(j, j)'''

    assert max_steps >= states.shape[0]
    # set states to fixed lenght with termination boolean to be able to compute termination error
    if states.shape[0] < max_steps:
        pad_idx = [(0,0) for i in range(states.ndim)]
        pad_idx[0] = (0, max_steps-states.shape[0])
        states = np.pad(states, pad_idx, 'edge')
        termination = np.pad(termination, (0, max_steps-termination.size), 'constant', constant_values=(1))
    history_dataset[i] = states
    terminations.append(termination)
    edges_mats.append(nx.to_numpy_matrix(graphs[i]))
    graphs[i] = dgl.DGLGraph(graphs[i])

# Take 10% of the graphs as validation
nb_val = int(0.1*nb_graphs)

train_data = [(graphs[i], edges_mats[i], history_dataset[i], terminations[i]) for i in range(nb_graphs-nb_val)]
test_data = [(graphs[i], edges_mats[i], history_dataset[i], terminations[i]) for i in range(nb_graphs-nb_val, nb_graphs)]

# Data loaders do not seem to be compatible with DGL
#train_loader = torch.utils.data.DataLoader(train_data)
#train_loader = torch.utils.data.DataLoader(test_data)

# dataset is an array of size batch size
# each idem is a history of shape (nb_steps, nb_nodes)
# We now have in our possession a full dataset on which to train


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

for epoch in range(nb_epochs):
    print('Epoch:', epoch)

    losses = []
    clock = time.time()

    for batch_idx, (graph, edges_mat, states, termination) in enumerate(train_data):
        if verbose: print('--- Processing new graph! ---')

        # We do optimizer call only after completely processing the graph
        #graph, states = graphs[i], history_dataset[i]
        # extract adjacency matrix
        #edges_mat = nx.to_numpy_matrix(graph)
        if verbose: print('edges_mat shape:', edges_mat.shape)
        # Convert graph to DGL
        #graph = dgl.DGLGraph(graph)


        if verbose: print('states shape (after reshape):', states.shape)
        if verbose: print('termination shape (after reshape):', termination.shape)

        states = torch.from_numpy(states)
        edges_mat = torch.from_numpy(edges_mat)

        # What exatly do we want as input?

        termination = torch.from_numpy(termination)

        if use_cuda:
            states, edges_mat, termination = states.cuda(), edges_mat.cuda(), termination.cuda()
        
        preds, pred_stops = model(graph, states, edges_mat)

        '''if batch_idx==1:
            print('states:', states)
            print('pred:', preds)
            print('termination:', termination)
            print('pred_stops:', pred_stops)'''

        #print(preds.size())
        #print(states.size())

        loss = nll_gaussian(preds, torch.t(states))
        loss += ((pred_stops-termination)**2).sum()/max_steps # MSE of output and states + termination loss

        optimizer.zero_grad()
        loss.backward()
        optimizer.step()

        losses.append(loss.item())

    print('Epoch run in:', time.time()-clock)
    clock = time.time()
    print('Loss:', np.mean(np.asarray(losses)))

print('states:', states)
print('pred:', torch.t(preds))
print('termination:', termination)
print('pred_stops:', pred_stops)