import torch
from torch.utils.data import DataLoader
import numpy as np
from tqdm import tqdm
import torch.nn as nn
import torch.nn.utils.prune as prune

from use import next_moves, prediction
from myModels import get_model
from myDatasets import transfer_back, channel_01, channel_2, transfer, channel_1015, get_datasets
from dataAnalyze import plot_board


def prune_model(model, prune_threshold):
    num_weights_before = 0
    for name, module in model.named_modules():
        if hasattr(module, 'weight') and (not getattr(module, 'weight') is None):
            num_weights_before += float(module.weight.nelement())
    for name, module in model.named_modules():
        if hasattr(module, 'weight') and (not getattr(module, 'weight') is None) and\
                not ("norm" in name) and not ("bn" in name):
            print(name)
            prune.l1_unstructured(module, name='weight', amount=prune_threshold)
            prune.remove(module, 'weight')
    num_weights_after = 0
    for name, module in model.named_modules():
        if hasattr(module, 'weight') and (not getattr(module, 'weight') is None):
            num_weights_after += float(torch.sum(module.weight == 0))
    print(num_weights_after/num_weights_before)
    return model

def score_legal(data_type, num_moves, model, device):
    first_steps = ["dd", "cd", "dc", "dp", "dq", "cp", "pd", "qd", 
                   "pc", "pp", "pq", "qp"]
    moves_score = 0
    score = 0
    full_score = len(first_steps)
    records = []
    for step in tqdm(first_steps, total = len(first_steps), leave = False):
        games = [[step]]
        datas = np.zeros([1,16,19,19],  dtype=np.float32)
        step = transfer(step)
        x = int(step / 19)
        y = int(step % 19)
        channel_01(datas, 0, x, y, len(games[0]))
        channel_2(datas, 0)
        while(len(games[0]) < num_moves):
            next_move = next_moves(data_type, num_moves, model, games, 1, device)[0]
            next_move_ch = transfer_back(next_move)
            x = int(next_move / 19)
            y = int(next_move % 19)
            if datas[0][2][x][y]:
                games[0].append(next_move_ch)
                channel_01(datas, 0, x, y, len(games[0]))
                channel_2(datas, 0)
            else:
                moves_score += len(games[0])
                break
        if len(games[0]) == num_moves:
            score += 1
            moves_score += num_moves
        records.append(games[0])
    return score, moves_score, full_score, records



def score_feature(data_type, num_moves, model, bounds):
    first_steps = ["dd", "cd", "dc", "dp", "dq", "cp", "pd", "qd", 
                   "pc", "pp", "pq", "qp"]
    nears = [0]*len(bounds)
    total = 0
    atari = 0
    liberty = 0
    records = []
    for step in tqdm(first_steps, total = len(first_steps), leave = False):
        games = [[step]]
        datas = np.zeros([1,16,19,19],  dtype=np.float32)
        f_step = transfer(step)
        x = int(f_step / 19)
        y = int(f_step % 19)
        lastx = x
        lasty = y
        channel_01(datas, 0, x, y, len(games[0]))
        channel_2(datas, 0)
        liberty += channel_1015(datas, 0, x, y, len(games[0]))
        while(len(games[0]) < num_moves):
            next_move = next_moves(data_type, num_moves, model, games, 1)[0]
            next_move_ch = transfer_back(next_move)
            x = int(next_move / 19)
            y = int(next_move % 19)
            if datas[0][2][x][y]:
                games[0].append(next_move_ch)
                channel_01(datas, 0, x, y, len(games[0]))
                channel_2(datas, 0)
                liberty += channel_1015(datas, 0, x, y, len(games[0]))
                total += 1
                # distance
                for i, bound in enumerate(bounds):
                    if (pow(lastx-x, 2) + pow(lasty-y, 2)) < bound*bound:
                        nears[i] += 1
                lastx = x
                lasty = y
                # atari
                p = 1
                if len(games[0]) % 2:
                    p = 0
                if x > 0 and datas[0][p][x-1][y] and datas[0][10][x-1][y]:
                    atari += 1
                if y > 0 and datas[0][p][x][y-1] and datas[0][10][x][y-1]:
                    atari += 1
                if x < 18 and datas[0][p][x+1][y] and datas[0][10][x+1][y]:
                    atari += 1
                if y < 18 and datas[0][p][x][y+1] and datas[0][10][x][y+1]:
                    atari += 1
            else:
                games[0].append(next_move_ch)
                break
        records.append(games[0])
    return [near/total for near in nears], atari/total, liberty/total


def myaccn_split(pred, true, n, split, num_move):
    correct = [0]*split
    for i, p in tqdm(enumerate(pred), total=len(pred), leave=False):
        sorted_indices = (-p).argsort()
        top_k_indices = sorted_indices[:n]  
        if true[i] in top_k_indices:
            correct[int((i%num_move)/int(num_move/split))] += 1
    part_total = len(true)/split
    for i in range(split):
        correct[i] /= part_total
    return correct 

def correct_pos(pred, true):
    correct = [0]*361
    total = [0]*361
    for i, p in tqdm(enumerate(pred), total=len(pred), leave=False):
        sorted_indices = (-p).argsort()
        total[sorted_indices[0]] += 1
        if true[i] == sorted_indices[0]:
            correct[sorted_indices[0]] += 1
    for i in range(361):
        if(total[i]):
            correct[i] /= total[i]
    return correct

def score_acc(data_config, model, split, device):
    batch_size = 64
    _, testData = get_datasets(data_config, train=False)
    test_loader = DataLoader(testData, batch_size=batch_size, shuffle=False)
    predl, true = prediction(data_config["data_type"], model, device, test_loader)
    acc10 = myaccn_split(predl, true, 10, split, data_config["num_moves"])
    acc5 = myaccn_split(predl, true, 5, split, data_config["num_moves"])
    acc1 = myaccn_split(predl, true, 1, split, data_config["num_moves"])
        
    return acc10, acc5, acc1

def correct_position(data_config, model, device):
    batch_size = 64
    _, testData = get_datasets(data_config, train=False)
    test_loader = DataLoader(testData, batch_size=batch_size, shuffle=False)
    predl, true = prediction(data_config["data_type"], model, device, test_loader)
    pos = correct_pos(predl, true)
    return pos, myaccn_split(predl, true, 1, 1, data_config["num_moves"])

def score_self(data_config, model, score_type, device):
    
    if score_type == "score":
        score, moves_score, full_score, records = score_legal(
            data_config["data_type"], data_config["num_moves"], model, device)
        print(records)
        print(f'score:{score}/{full_score}')
        print(f'moves_score:{moves_score/full_score}/{data_config["num_moves"]}')
    elif score_type == "feature":
        bounds = [1.5, 2.9, 4.3, 5.7, 7.1, 8.5]
        near, atari, liberty = score_feature(
            data_config["data_type"], data_config["num_moves"], model, bounds)
        print(f'near:{near}')
        print(f'atari:{atari}')
        print(f'liberty:{liberty}')
    elif score_type == "score_acc":
        #use test data
        split = 1
        acc10, acc5, acc1 = score_acc(data_config, model, split, device)
        print(acc10)
        print(acc5)
        print(acc1)
    elif score_type == "correct_pos":
        #use eval data
        pos, acc1 = correct_position(data_config, model, device)
        plot_board(pos)
        print(pos)
        print(acc1)

 
if __name__ == "__main__":
    data_config = {}
    data_config["path"] = 'datas/data_240119.csv'
    data_config["data_size"] = 350
    data_config["offset"] = 0
    data_config["data_type"] = "Picture"
    data_config["data_source"] = "pros"
    data_config["num_moves"] = 240

    model_config = {}
    model_config["model_name"] = "ResNet"
    model_config["model_size"] = "mid"

    score_type = "score_acc"
    device = "cuda:1"
   
    state = torch.load(f'models_240/ResNet1_10000.pt')
    model = get_model(model_config).to(device)
    model.load_state_dict(state)
    model = prune_model(model, 0.1)
    score_self(data_config, model, score_type, device)
    
   
    