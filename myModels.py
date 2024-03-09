from transformers import BertModel, BertConfig, BertForPreTraining, BertForSequenceClassification
import torch.nn as nn
import torch
import yaml
import torch.nn.functional as F
from transformers import ViTModel, ViTConfig, Swinv2Config, Swinv2Model
from safetensors import safe_open


class Bert_Go(nn.Module):
    def __init__(self, config, num_labels, p_model = None):
        super(Bert_Go, self).__init__()
        if p_model is None:
            self.bert = BertModel(config)
        else:
            self.bert = p_model
        self.linear1 = nn.Linear(config.hidden_size, 512)
        self.linear2 = nn.Linear(512, num_labels)
    def forward(self, x, m):
        output = self.bert(input_ids=x, attention_mask=m)["last_hidden_state"]
        logits = torch.mean(output, dim=1)
        logits = self.linear1(logits)
        logits = self.linear2(logits)
        return logits
    
    
class ConvBlock(nn.Module):
    def __init__(self, in_channels, out_channels, kernal_size):
        super(ConvBlock, self).__init__()
        self.cnn = nn.Conv2d(in_channels, out_channels, kernel_size=kernal_size, padding=int((kernal_size-1)/2))
        self.bn = nn.BatchNorm2d(out_channels, affine=False)
        self.beta = nn.Parameter(torch.zeros(out_channels))  
        nn.init.kaiming_normal_(self.cnn.weight, mode="fan_out", nonlinearity="relu")
    def forward(self, x):
        x = self.cnn(x)
        x = self.bn(x)
        x += self.beta.view(1, self.bn.num_features, 1, 1).expand_as(x)
        return x
    
class ResBlock(nn.Module):
    def __init__(self, in_channels, out_channels):
        super(ResBlock, self).__init__()
        self.cnn1 = ConvBlock(in_channels, out_channels, 3)
        self.cnn2 = ConvBlock(out_channels, out_channels, 3)
        self.relu = nn.ReLU()
    def forward(self, x):
        identity = x
        out = F.relu(self.cnn1(x), inplace=True)
        out = self.cnn2(out)
        out += identity
        return F.relu(out, inplace=True)

class myResNet(nn.Module):
    def __init__(self, in_channels, res_channels, res_layers):
        super(myResNet, self).__init__()
        self.cnn_input = ConvBlock(in_channels, res_channels, 3)
        self.residual_tower = nn.Sequential(
            *[ResBlock(res_channels, res_channels) for _ in range(res_layers)]
        )
        self.policy_cnn = ConvBlock(res_channels, 2, 1)
        self.policy_fc = nn.Linear(2 * 19 * 19, 19 * 19)
        #self.value_cnn = ConvBlock(res_channels, 1, 1)
        #self.value_fc_1 = nn.Linear(19 * 19, 256)
        #self.value_fc_2 = nn.Linear(256, 1)
    def forward(self, planes):
        x = self.cnn_input(planes)
        x = self.residual_tower(x)
        pol = self.policy_cnn(x)
        pol = self.policy_fc(torch.flatten(pol, start_dim=1))
        #val = self.value_cnn(x)
        # = F.relu(self.value_fc_1(torch.flatten(val, start_dim=1)), inplace=True)
        #val = torch.tanh(self.value_fc_2(val))
        return pol#, val


class myViT(nn.Module):
    def __init__(self, config, channels_in, cnn_channels, kernal_size):
        super(myViT, self).__init__()
        self.vit = ViTModel(config)
        self.pool = nn.Linear(config.hidden_size,1)
        self.linear = nn.Linear(362, 361)
        self.cnn1 = nn.Conv2d(channels_in,cnn_channels,kernel_size=kernal_size, padding=int((kernal_size-1)/2))
        self.cnn2 = nn.Conv2d(cnn_channels,config.hidden_size,kernel_size=kernal_size, padding=int((kernal_size-1)/2))
        self.bn1 = nn.BatchNorm2d(cnn_channels)
        self.bn2 = nn.BatchNorm2d(config.hidden_size)
    def forward(self, x):
        y = self.cnn1(x)
        y = self.bn1(y)
        y = self.cnn2(y)
        y = F.relu(self.bn2(y),inplace=True)
        y = self.vit(y)
        y = y["last_hidden_state"]
        y = self.pool(y).squeeze(2)
        y = self.linear(y)
        return y


class Mix(nn.Module):
    def __init__(self, models):
        super(Mix, self).__init__()
        self.models = models
        self.output = nn.Linear(361*len(models),361)
    def forward(self, x):
        y = []
        for model in self.models:
            y.append(model(x))
        y = torch.cat(y,dim = -1)
        y = self.output(y)
        return y
    
class myST(nn.Module):
    def __init__(self, config, channels_in, cnn_channels, kernal_size):
        super(myST, self).__init__()
        self.st = Swinv2Model(config)
        output_len = config.embed_dim
        depth = config.num_layers-1
        while(depth > 0):
            depth -= 1
            output_len *= 2
        self.linear1 = nn.Linear(output_len, 512)
        self.linear2 = nn.Linear(512, 361)
        self.cnn = nn.Conv2d(channels_in,cnn_channels,kernel_size=kernal_size, padding=int((kernal_size-1)/2))
        self.bn = nn.BatchNorm2d(cnn_channels)
 
    def forward(self, x):
        y = self.cnn(x)
        y = F.relu(self.bn(y),inplace=True)
        y = self.st(y)
        y = y["last_hidden_state"]
        y = torch.mean(y, dim=1)
        y = self.linear1(y)
        y = self.linear2(y)
        return y


def get_model(name, level, state_path = None, config_path = None):
    with open('modelArgs.yaml', 'r') as file:
        args = yaml.safe_load(file)
    if not ("x" in name):
        args = args[name][level]

    if name == 'BERT':
        config = BertConfig() 
        config.hidden_size = args["hidden_size"]
        config.num_hidden_layers = args["num_hidden_layers"]
        config.vocab_size = 364
        config.num_attention_heads = 1
        config.intermediate_size = config.hidden_size*4
        config.position_embedding_type = "relative_key"
        model = Bert_Go(config, 361)
    elif name == "BERTp":
        config = BertConfig() 
        config.hidden_size = args["hidden_size"]
        config.num_hidden_layers = args["num_hidden_layers"]
        config.vocab_size = 365
        config.num_attention_heads = 1
        config.intermediate_size = config.hidden_size*4
        config.position_embedding_type = "relative_key"
        model = Bert_Go(config, 361)
    elif name == "BERTxpretrained":
        tensors = {}
        with safe_open(state_path, framework="pt") as f:
            for k in f.keys():
                split_k = k.split('.')
                if split_k[0] == 'bert':
                    kk = k[5:]
                else:
                    kk = k
                tensors[kk] = f.get_tensor(k)
        keys_to_delete = ["cls.predictions.bias", "cls.predictions.transform.LayerNorm.bias", "cls.predictions.transform.LayerNorm.weight",
                            "cls.predictions.transform.dense.bias", "cls.predictions.transform.dense.weight", "cls.seq_relationship.bias", "cls.seq_relationship.weight"]
        for key in keys_to_delete:
            del tensors[key]
        config = BertConfig.from_json_file(config_path)
        pretrained_model = BertModel(config)
        pretrained_model.load_state_dict(tensors)
        model = Bert_Go(config, 361, pretrained_model)
    elif name == 'pretrainxBERT':
        args = args['BERT'][level]
        config = BertConfig() 
        config.hidden_size = args["hidden_size"]
        config.num_hidden_layers = args["num_hidden_layers"]
        config.vocab_size = 365
        config.num_attention_heads = 1
        config.intermediate_size = config.hidden_size*4
        config.position_embedding_type = "relative_key"
        model = BertForPreTraining(config)

    elif name == 'ResNet':
        res_channel = args["res_channel"]
        layers = args["layers"]
        in_channel = 16
        model = myResNet(in_channel, res_channel, layers)
    elif name == 'ViT':
        config = ViTConfig()
        cnn_channel = args["cnn_channel"]
        config.num_channels = args["vit_channels"]
        config.hidden_size = args["hidden_size"]
        config.num_hidden_layers = args["num_hidden_layers"]
        
        in_channel = 16
        config.image_size = 19
        config.patch_size = 1
        config.encoder_stride = 1
        config.num_attention_heads = 1
        config.hidden_dropout_prob = 0.1
        config.intermediate_size = config.hidden_size* 4 
        config.attention_probs_dropout_prob = 0.1
        kernal_size = 3
        model = myViT(config, in_channel, cnn_channel, kernal_size)
    elif name == "ST":
        config = Swinv2Config()
        config.num_layers = args["num_layers"]
        config.num_heads = args["num_heads"]
        config.depths = args["depths"]
        config.num_channels = args["cnn_channels"]
        
        in_channel = 16
        kernal_size = 7
        config.image_size = 19
        config.patch_size = 1
        config.embed_dim = 64
        config.encoder_stride = 1
        model = myST(config, in_channel, config.num_channels, kernal_size)
    elif name == 'Mix':
        model1 = get_model("ST", level)
        model2 = get_model("ViT", level)
        model3 = get_model("ResNet", level)
        model = Mix([model1, model2, model3])
    return model

if __name__ == "__main__":
    model = get_model("GPT", "other")
    total_params = sum(p.numel() for p in model.parameters())
    print(f"Total Parameters: {total_params}")