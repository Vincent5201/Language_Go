import numpy as np
from tqdm import tqdm
import torch
import matplotlib.pyplot as plt

from myDatasets import get_datasets
from myModels import get_model

def cosine_similarity(vec1, vec2):
    magnitude_vec1 = np.linalg.norm(vec1)
    magnitude_vec2 = np.linalg.norm(vec2)
    if magnitude_vec1 != 0 and magnitude_vec2 != 0:
        similarity = np.dot(vec1, vec2) / (magnitude_vec1 * magnitude_vec2)
    else:
        similarity = 0
    return similarity

def euclidean_distance(vec1, vec2):
    return np.sqrt(np.sum((vec1 - vec2) ** 2))

def embedding_distance(data_config, model_config):
    if data_config["data_type"] != "Word":
        print("wrong data type")
        return
    _, testData = get_datasets(data_config, 1, train=False)
    games = torch.stack([testData.x[80*i+79] for i in range(int(len(testData.x)/80))])
    print(games.shape)
    model = get_model(model_config)
    state = torch.load(f'models_{data_config["num_moves"]}/BERT1_30000.pt')
    model.load_state_dict(state)

    mat = np.zeros((361,361))
    count = np.zeros((361,361))
    model.eval()
    embedding_weights = model.bert.get_input_embeddings()
    input_embeddings = embedding_weights(games).detach().numpy()
    for i, (game, game_v) in tqdm(enumerate(zip(games, input_embeddings)), total=len(games), leave=False):
        for j, (move, move_v) in enumerate(zip(game, game_v)):
            if move and move < 362:
                move -= 1
                for k, (move2, move_v2) in enumerate(zip(game, game_v)):
                    if k > j and move2 and move2 < 362 and move != move2:
                        move2 -= 1
                        #simi = cosine_similarity(move_v, move_v2)
                        dis = euclidean_distance(move_v, move_v2)
                        mat[move][move2] += dis
                        count[move][move2] += 1
                        mat[move2][move] += dis
                        count[move2][move] += 1
    for i in range(361):
        for j in range(361):
            if count[i][j]:
                mat[i][j] /= count[i][j]
    np.save('analyzation_data/dis.npy', mat)

    return mat

def data_similarity(data_config):
    _, testData = get_datasets(data_config, 1, train=False)
    games = torch.stack([testData.x[80*i+79] for i in range(int(len(testData.x)/80))]).cpu().numpy()
    print(games.shape)
    counts = [0]*(data_config["num_moves"]+1)
    records = np.zeros((len(games), 361))
    for i, game in tqdm(enumerate(games), total=len(games), leave=False):
        for p in range(19):
            for q in range(19):
                if game[0][p][q]:
                    records[i][19*p+q] = 1
                elif game[1][p][q]:
                    records[i][19*p+q] = -1
    print("records end")
    for i, record1 in tqdm(enumerate(records), total=len(records), leave=False):
        for j, record2 in enumerate(records):
            if j > i:
                counts[np.sum((record1 != 0) & (record1 == record2))] += 1
    print(counts)
    return counts

def check_atari(game, x, y, p):
    pp = 1
    if p:
        pp = 0
    count = 0
    if x > 0 and x < 18 and y > 0 and y < 18:
        if game[p][x-1][y] or game[p][x+1][y] or game[p][x][y-1] or game[p][x][y+1]:
            return -1
        if game[pp][x-1][y+1] or game[pp][x+1][y-1] or game[pp][x-1][y-1] or game[pp][x+1][y+1]:
            return -1

        if game[pp][x-1][y]:
            count += 1
        if game[pp][x+1][y]:
            count += 1
        if game[pp][x][y-1]:
            count += 1
        if game[pp][x][y+1]:
            count += 1
        if count == 3:
            return x*19+y
    return -1
    
def plot_board(mat):
    mat = np.array(mat).reshape(19,19)
    cmap = plt.get_cmap('coolwarm')
    plt.imshow(mat, cmap=cmap)
    plt.colorbar()
    plt.show()

def find_atari(games, trues):
    pos = [0]*361
    games = games.cpu().numpy()
    for i, game in tqdm(enumerate(games), total=len(games), leave=False):
        x = int(trues[i]/19)
        y = int(trues[i]%19)
        if x > 0 and game[i%2][x-1][y] and game[10][x-1][y]:
            ret = check_atari(game, x-1, y, i%2)
            if ret != -1:
                pos[ret] += 1
        if x < 18 and game[i%2][x+1][y] and game[10][x+1][y]:
            ret = check_atari(game, x+1, y, i%2)
            if ret != -1:
                pos[ret] += 1
        if y > 0 and game[i%2][x][y-1] and game[10][x][y-1]:
            ret = check_atari(game, x, y-1, i%2)
            if ret != -1:
                pos[ret] += 1
        if y < 18 and game[i%2][x][y+1] and game[10][x][y+1]:
            ret = check_atari(game, x, y+1, i%2)
            if ret != -1:
                pos[ret] += 1

    plot_board(pos)
    return

def pred_analyze(predls, trues):
    
    records = [[0]*4 for _ in range(5)]
    print("start classiy")
    for j in tqdm(range(len(trues)), total=len(trues), leave=False):
        choose = [(-(predls[i][j])).argsort()[0] for i in range(3)]
        p = 0
        if choose[0] == choose[1]:
            if choose[0] == choose[2]:
                p = 4
            else:
                p = 1
        elif choose[0] == choose[2]:
            p = 2
        elif choose[1] == choose[2]:
            p = 3
        if p == 0:
            if trues[j] == choose[0]:
                records[p][0] += 1
            elif trues[j] == choose[1]:
                records[p][1] += 1
            elif trues[j] == choose[2]:
                records[p][2] += 1
            else:
                records[p][3] += 1
        elif p == 1:
            if trues[j] == choose[0]:
                records[p][0] += 1
            elif trues[j] == choose[2]:
                records[p][1] += 1
            else:
                records[p][2] += 1
        elif p == 2:
            if trues[j] == choose[0]:
                records[p][0] += 1
            elif trues[j] == choose[1]:
                records[p][1] += 1
            else:
                records[p][2] += 1
        elif p == 3:
            if trues[j] == choose[1]:
                records[p][0] += 1
            elif trues[j] == choose[0]:
                records[p][1] += 1
            else:
                records[p][2] += 1
        else:
            if trues[j] == choose[0]:
                records[p][0] += 1
            else:
                records[p][1] += 1
    print(records)
    return records




if __name__ == "__main__":
    data_config = {}
    data_config["path"] = 'D:\codes\python\.vscode\Transformer_Go\datas\data_240119.csv'
    data_config["data_size"] = 30000
    data_config["offset"] = 0
    data_config["data_type"] = "Word"
    data_config["data_source"] = "pros"
    data_config["num_moves"] = 80

    model_config = {}
    model_config["model_name"] = "BERT"
    model_config["model_size"] = "mid"
    model_config["config_path"] = "models_160/p1/config.json"
    model_config["state_path"] = "models_160/p1/model.safetensors"

    device = "cuda:1"
    
    #with open('D:/codes/python/.vscode/Transformer_Go/analyzation.yaml', 'r') as file:
     #   data = yaml.safe_load(file)["data_similarity"]
    #data = np.log2(np.array(data) + 1)
    #plot_array(data)

    mat = np.load('D:/codes/python/.vscode/Transformer_Go/analyzationData/cos_simi.npy')
    mat[180][180] = 0
    plot_board(mat[180])