import torch
from torch.utils.data import DataLoader
import numpy as np
from tqdm import tqdm
import copy
import math
import random
import yaml

from use import prediction
from get_datasets import get_datasets
from get_models import get_model
from tools import *

def class_correct_moves(predls, true, n):
    l = len(predls)
    records = [[] for _ in range(2**l)]
    print("start classiy")
    for j in tqdm(range(len(true)), total=len(true), leave=False):
        pos = 0
        for i in range(l):
            pos *= 2
            sorted_indices = (-(predls[i][j])).argsort()
            top_k_indices = sorted_indices[:n]  
    
            if true[j] in top_k_indices:
                pos += 1
        records[pos].append(j)
    return records

def vote_model(sorted_indices, choose):
    top_choices = [p[0] for p in sorted_indices]
    if len(top_choices) == len(set(top_choices)):
        choices = [top_choices[choose]]
    else:
        if len(set(top_choices)) == 1:
            choices = [top_choices[0]]
        else:
            if top_choices[0] == top_choices[1]:
                choices = [top_choices[0]]
            elif top_choices[0] == top_choices[2]:
                choices = [top_choices[0]]
            else:
                choices = [top_choices[1]]
    return choices

def prob_vote(sorted_indices, sorted_p):
    vote = {}
    for p, indices in enumerate(sorted_indices):
        for q, indice in enumerate(indices):
            if indice in vote.keys():
                vote[indice] += sorted_p[p][q]
            else:
                vote[indice] = sorted_p[p][q]
    sorted_vote = dict(sorted(vote.items(), key=lambda item: item[1], reverse=True))
    choices = list(sorted_vote.keys())
    return choices

def prob_rank_vote(sorted_indices, sorted_p):
    prob_vote = {}
    rank_vote = {}
    for p, indices in enumerate(sorted_indices):
        for q, indice in enumerate(indices):
            if indice in prob_vote.keys():
                prob_vote[indice] += sorted_p[p][q]
            else:
                prob_vote[indice] = sorted_p[p][q]
            if indice in rank_vote.keys():
                if p:
                    rank_vote[indice] += (0.9-q/10)
                else:
                    rank_vote[indice] += (1-q/10)
            else:
                if p:
                    rank_vote[indice] = (0.9-q/10)
                else:
                    rank_vote[indice] = (1-q/10)
    sorted_prob = dict(sorted(prob_vote.items(), key=lambda item: item[1], reverse=True))
    sorted_rank = dict(sorted(rank_vote.items(), key=lambda item: item[1], reverse=True))
    probs = list(sorted_prob.keys())[:5]
    ranks = list(sorted_rank.keys())[:5]
    comb_vote = {}
    for i, indice in enumerate(probs):
        if indice in comb_vote.keys():
            comb_vote[indice] += (0.95-i*i/10)
        else:
            comb_vote[indice] = (0.95-i*i/10)
    for i, indice in enumerate(ranks):
        if indice in comb_vote.keys():
            comb_vote[indice] += (1-i*i/10)
        else:
            comb_vote[indice] = (1-i*i/10)
    sorted_comb = dict(sorted(comb_vote.items(), key=lambda item: item[1], reverse=True))
    combs = list(sorted_comb.keys())[:5]
    return combs

def rank_vote(sorted_indices):
    vote = {}
    for p, indices in enumerate(sorted_indices):
        for q, indice in enumerate(indices):
            if indice in vote.keys():
                if p:
                    vote[indice] += (0.9-q/10)
                else:
                    vote[indice] += (1-q/10)
            else:
                if p:
                    vote[indice] = (0.9-q/10)
                else:
                    vote[indice] = (1-q/10)
    sorted_vote = dict(sorted(vote.items(), key=lambda item: item[1], reverse=True))
    choices = list(sorted_vote.keys())
    return choices

def get_data_pred(data_config, models, data_types, device):
    batch_size = 64
    predls = []
    data_config["data_type"] = "Word"
    _, testDataW = get_datasets(data_config, train=False)
    test_loaderW = DataLoader(testDataW, batch_size=batch_size, shuffle=False)
    trues = testDataW.y

    data_config["data_type"] = "Picture"
    _, testDataP = get_datasets(data_config, train=False)
    test_loaderP = DataLoader(testDataP, batch_size=batch_size, shuffle=False)
    for i, model in enumerate(models):
        if data_types[i] == "Word":
            predl, _ = prediction(data_types[i], model, device, test_loaderW)
        else:
            predl, _ = prediction(data_types[i], model, device, test_loaderP)
        predls.append(predl)
    

    return testDataP, testDataW, predls, trues.cpu().numpy()

def mix_acc(n, data_config, predls, trues, smart=None):
    total = len(trues)
    correct = 0
    for i in tqdm(range(total), total=total, leave=False):
        sorted_indices = []
        sorted_p = []
        for _, predl in enumerate(predls):
            sorted_indices.append((-predl[i]).argsort()[:5]) 
            sorted_p.append(np.sort(predl[i])[::-1][:5])
        
        choices = []
        if smart == "prob_vote":
            choices = prob_vote(sorted_indices, sorted_p)
        elif smart == "vote+ResNet":
            choices = vote_model(sorted_indices, 0)
        elif smart == "rank_vote":
            choices = rank_vote(sorted_indices)
        elif smart == "prob_rank_vote":
            choices = prob_rank_vote(sorted_indices, sorted_p)
        else:
            choices = [s[0] for s in sorted_indices]
            random.shuffle(choices)
        if trues[i] in choices[:n]:
            correct += 1

    return correct/total

def compare_correct(predls, trues):
    record1 = class_correct_moves(predls, trues, 1)
    total = len(trues)
    count = [len(record)/total for record in record1]

    return record1, count

def score_more(data_config, models, device, score_type):

    testDataP, testDataW, predls, trues = get_data_pred(data_config, models, data_types, device)
    #predls = np.load('analyzation_data/prediction4_30000_s8596.npy')
    #trues = np.load('analyzation_data/trues4_s8596.npy')

    if score_type == "compare_correct":
        records, count = compare_correct(predls, trues)
        print(count)
        #print(records)
    elif score_type == "mix_acc":
        acc = mix_acc(1, data_config, predls, trues, "rank_vote")
        print(acc)
        acc = mix_acc(1, data_config, predls, trues, "prob_rank_vote")
        print(acc)
    elif score_type == "acc+compare":
        records, count = compare_correct(predls, trues)
        print(count)
        acc = mix_acc(1, data_config, predls, trues, "prob_vote")
        print(acc)
        acc = mix_acc(1, data_config, predls, trues, "prob_rank_vote")
        print(acc)


if __name__ == "__main__":
    data_config = {}
    data_config["path"] = 'datas/data_240119.csv'
    data_config["data_size"] = 35000
    data_config["offset"] = 0
    data_config["data_type"] = "Picture"
    data_config["data_source"] = "pros"
    data_config["num_moves"] = 240

    model_config = {}
    model_config["model_name"] = "ST"
    model_config["model_size"] = "mid"

    device = "cuda:1"
    score_type = "mix_acc"

    data_types = ['Picture', 'Picture', 'Picture']
    model_names = ["ResNet", "ViT", "ST"] #abc
    states = [f'models_{data_config["num_moves"]}/ResNet1_10000.pt',
              f'models_{data_config["num_moves"]}/ViT1_10000.pt',
              f'models_{data_config["num_moves"]}/ST1_10000.pt']
              #f'models_{data_config["num_moves"]}/BERT1_s27_30000.pt'
    models = []
    for i in range(len(model_names)):
        model_config["model_name"] = model_names[i]
        model = get_model(model_config).to(device)
        state = torch.load(states[i])
        model.load_state_dict(state)
        models.append(model)

    get_data_pred(data_config, models, data_types, device)

   
    