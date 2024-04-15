import torch
from torch.utils.data import DataLoader
import numpy as np
from tqdm import tqdm
import random

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

def mix_acc(n, predls, trues, smart=None, board=None):
    total = len(trues)
    correct = 0
    for i in tqdm(range(total), total=total, leave=False):
        sorted_indices = []
        sorted_p = []
        for _, predl in enumerate(predls):
            tmp_idx = (-predl[i]).argsort()[:max(3*n,5)]
            tmp_p = np.sort(predl[i])[::-1][:max(3*n,5)]
            if not board is None:
                tmp_p = [p for idx, p in zip(tmp_idx, tmp_p)\
                            if board[i][2][int(idx/19)][int(idx%19)]][:max(3*n,5)]
                tmp_idx = [idx for idx in tmp_idx\
                                if board[i][2][int(idx/19)][int(idx%19)]][:max(3*n,5)]
            sorted_indices.append(tmp_idx) 
            sorted_p.append(tmp_p)
    
        choices = []
        if smart == "prob_vote":
            choices = prob_vote(sorted_indices, sorted_p)
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

def compare_correct(predls, trues, n):
    record1 = class_correct_moves(predls, trues, n)
    total = len(trues)
    count = [len(record)/total for record in record1]

    return record1, count

def invalid_rate(board, predls, n=1):
    total = len(predls[0])
    invalid = [0]*len(predls)
    for i in tqdm(range(total), total=total, leave=False):
        for j, predl in enumerate(predls):
            chooses = (-predl[i]).argsort()[:n]
            check = True
            for c in chooses:
                if board[i][2][int(c/19)][int(c%19)]:
                    check = False
                    break
            if check:
                invalid[j] += 1
    return [e/total for e in invalid]
            
def score_more(data_config, models, device, score_type):

    testDataP, testDataW, predls, trues = get_data_pred(data_config, models, data_types, device)
    #predls = np.load('analyzation_data/prediction4_30000_s8596.npy')
    #trues = np.load('analyzation_data/trues4_s8596.npy')

    if score_type == "compare_correct":
        records, count = compare_correct(predls, trues)
        print(count)
        #print(records)
    elif score_type == "mix_acc":
        acc = mix_acc(1, predls, trues, "rank_vote")
        print(acc)
        acc = mix_acc(1, predls, trues, "prob_rank_vote")
        print(acc)
    elif score_type == "acc+compare":
        records, count = compare_correct(predls, trues, 5)
        print(count)
        acc = mix_acc(5, predls, trues, "prob_vote")
        print(acc)
    elif score_type == "invalid":
        invalid = invalid_rate(testDataP.x, predls, 10)
        print(invalid)
    elif score_type == "mix_acc_valid":
        acc = mix_acc(1, predls, trues, "prob_vote", testDataP.x)
        print(acc)
        
if __name__ == "__main__":
    data_config = {}
    data_config["path"] = 'datas/data_240119.csv'
    data_config["data_size"] = 35000
    data_config["offset"] = 0
    data_config["data_type"] = "Picture"
    data_config["data_source"] = "pros"
    data_config["num_moves"] = 240
    data_config["extend"] = False

    model_config = {}
    model_config["model_name"] = "ST"
    model_config["model_size"] = "mid"

    device = "cuda:0"
    score_type = "mix_acc_valid"

    data_types = ['Picture', 'Word']
    model_names = ["ResNet", "BERTp"] #abc
    states = [f'models/ResNet/mid_5000.pt',
              f'models/BERT/mid_s27_30000.pt']
    models = []
    for i in range(len(model_names)):
        model_config["model_name"] = model_names[i]
        model = get_model(model_config).to(device)
        state = torch.load(states[i])
        model.load_state_dict(state)
        models.append(model)

    #get_data_pred(data_config, models, data_types, device)
    score_more(data_config, models, device, score_type)
   
    