import time
import numpy as np

import torch
import torch.nn
import torch.nn.functional as F
import torchvision.models

import torch_geometric.data
from torch_geometric.nn import GCNConv, global_mean_pool
from torch_geometric.data import DataLoader

from retrieval import networks
from retrieval.netvlad import NetVLAD, EmbedNet

'''
TODO: 
-other backbone?
-other and/or separate embedding dims?
'''

def create_image_model_vgg11():
    vgg=torchvision.models.vgg11(pretrained=True)
    for i in [4,5,6]: vgg.classifier[i]=torch.nn.Identity()     
    return vgg

def create_image_model_netvlad():
    NUM_CLUSTERS=8
    ALPHA=10.0
    encoder=networks.get_encoder_resnet18()
    encoder.requires_grad_(False) #Don't train encoder
    netvlad_layer=NetVLAD(num_clusters=NUM_CLUSTERS, dim=512, alpha=ALPHA)
    model=EmbedNet(encoder, netvlad_layer)

    model_name='model_netvlad_l3000_b6_g0.75_c8_a10.0.pth'
    model.load_state_dict(torch.load('models/'+model_name)) 
    return model   

class VisualGraphEmbedding(torch.nn.Module):
    def __init__(self,image_model, embedding_dim):
        super(VisualGraphEmbedding, self).__init__()

        self.embedding_dim=embedding_dim

        #Graph layers
        self.conv1 = GCNConv(self.embedding_dim, self.embedding_dim)
        self.conv2 = GCNConv(self.embedding_dim, self.embedding_dim)
        self.conv3 = GCNConv(self.embedding_dim, self.embedding_dim)

        self.node_embedding=torch.nn.Embedding(30, self.embedding_dim) #30 should be enough
        self.node_embedding.requires_grad_(False) # Performance proved better w/o training the Embedding ✓

        self.image_model=image_model
        self.image_model.requires_grad_(False)
        self.image_model.eval()
        #self.image_dim=image_model.dim*image_model.num_clusters #Output gets flattened during NetVLAD
        self.image_dim=list(image_model.parameters())[-1].shape[0] #For VGG
        assert self.image_dim==4096        
        
        self.W_g=torch.nn.Linear(self.embedding_dim, self.embedding_dim, bias=True) #TODO: normally w/o this!
        self.W_i=torch.nn.Linear(self.image_dim,self.embedding_dim,bias=True)

    def forward(self, images, graphs):
        #assert len(graphs)==len(images)

        out_images=self.encode_images(images)
        out_graphs=self.encode_graphs(graphs)
        assert out_images.shape==out_graphs.shape

        return out_images, out_graphs

    def encode_images(self, images):
        assert len(images.shape)==4 #Expect a batch of images
        q=self.image_model(images)
        x=self.W_i(q)
        x=x/torch.norm(x, dim=1, keepdim=True)

        return x

    def encode_graphs(self, graphs):
        #x, edges, edge_attr, batch = graphs.x, graphs.edge_index, graphs.edge_attr, graphs.batch
        
        x = self.node_embedding(graphs.x) #CARE: is this ok? X seems to be simply stacked
        edges=graphs.edge_index
        edge_attr=graphs.edge_attr
        batch=graphs.batch

        x = self.conv1(x, edges, edge_attr)
        x = F.relu(x)
        x = self.conv2(x, edges, edge_attr)
        x = F.relu(x)
        x = self.conv3(x, edges, edge_attr)
        x = global_mean_pool(x, batch)  # [batch_size, hidden_channels]

        x = self.W_g(x)

        x=x/torch.norm(x, dim=1, keepdim=True)
        
        return x
   
class VisualGraphEmbeddingNetVLAD(torch.nn.Module):
    def __init__(self,image_model, embedding_dim):
        super(VisualGraphEmbeddingNetVLAD, self).__init__()

        self.embedding_dim=embedding_dim

        #Graph layers
        self.conv1 = GCNConv(self.embedding_dim, self.embedding_dim)
        self.conv2 = GCNConv(self.embedding_dim, self.embedding_dim)
        self.conv3 = GCNConv(self.embedding_dim, self.embedding_dim)

        self.node_embedding=torch.nn.Embedding(30, self.embedding_dim) #30 should be enough
        self.node_embedding.requires_grad_(False) # Performance proved better w/o training the Embedding ✓

        self.image_model=image_model
        self.image_model.requires_grad_(False)
        self.image_model.eval()
        self.image_dim=image_model.net_vlad.dim*image_model.net_vlad.num_clusters #Output get's flattened during NetVLAD
        print('Image_Dim',self.image_dim)
        assert self.image_dim==4096        
        
        self.W_g=torch.nn.Linear(self.embedding_dim, self.embedding_dim, bias=True) # From NetVLAD-output to embedding
        self.W_i=torch.nn.Linear(self.image_dim,self.embedding_dim,bias=True) #From Graph-output to embedding

    def forward(self, images, graphs):
        #assert len(graphs)==len(images)

        out_images=self.encode_images(images)
        out_graphs=self.encode_graphs(graphs)
        assert out_images.shape==out_graphs.shape

        return out_images, out_graphs

    def encode_images(self, images):
        assert len(images.shape)==4 #Expect a batch of images
        x=self.image_model(images)
        x=self.W_i(x)

        x=x/torch.norm(x, dim=1, keepdim=True)

        return x

    def encode_graphs(self, graphs):
        #x, edges, edge_attr, batch = graphs.x, graphs.edge_index, graphs.edge_attr, graphs.batch
        
        x = self.node_embedding(graphs.x) #CARE: is this ok? X seems to be simply stacked
        edges=graphs.edge_index
        edge_attr=graphs.edge_attr
        batch=graphs.batch

        x = self.conv1(x, edges, edge_attr)
        x = F.relu(x)
        x = self.conv2(x, edges, edge_attr)
        x = F.relu(x)
        x = self.conv3(x, edges, edge_attr)
        x = global_mean_pool(x, batch)  # [batch_size, hidden_channels]

        x = self.W_g(x)

        x=x/torch.norm(x, dim=1, keepdim=True)
        
        return x   

class VisualGraphEmbeddingCombined(torch.nn.Module):
    def __init__(self,image_model, embedding_dim):
        super(VisualGraphEmbeddingCombined, self).__init__()

        self.embedding_dim=embedding_dim

        #Graph layers
        self.conv1 = GCNConv(self.embedding_dim, self.embedding_dim)
        self.conv2 = GCNConv(self.embedding_dim, self.embedding_dim)
        self.conv3 = GCNConv(self.embedding_dim, self.embedding_dim)

        self.node_embedding=torch.nn.Embedding(30, self.embedding_dim) #30 should be enough
        self.node_embedding.requires_grad_(False) # Performance proved better w/o training the Embedding ✓

        self.image_model=image_model
        self.image_model.requires_grad_(False)
        self.image_model.eval()
        #self.image_dim=image_model.dim*image_model.num_clusters #Output gets flattened during NetVLAD
        self.image_dim=list(image_model.parameters())[-1].shape[0] #For VGG
        assert self.image_dim==4096        
        
        #self.W_g=torch.nn.Linear(self.embedding_dim, self.embedding_dim, bias=True) #TODO: normally w/o this!
        #self.W_i=torch.nn.Linear(self.image_dim,self.embedding_dim,bias=True)
        self.W_combine=torch.nn.Linear(self.image_dim+self.embedding_dim,self.embedding_dim,bias=True)

    def forward(self, images, graphs):
        #assert len(graphs)==len(images)

        out_images=self.encode_images(images)
        out_graphs=self.encode_graphs(graphs)
        #print(out_images.shape, out_graphs.shape)
        assert out_images.shape[0]==out_graphs.shape[0]

        out_combined=self.W_combine( torch.cat((out_images, out_graphs), dim=1) ) #Concatenate along dim1 (4096+1024)
        out_combined=out_combined/torch.norm(out_combined, dim=1, keepdim=True)

        return out_combined
        
    def encode_images(self, images):
        assert len(images.shape)==4 #Expect a batch of images
        x=self.image_model(images)
        #x=self.W_i(q)
        #x=x/torch.norm(x, dim=1, keepdim=True)

        return x

    def encode_graphs(self, graphs):
        #x, edges, edge_attr, batch = graphs.x, graphs.edge_index, graphs.edge_attr, graphs.batch
        
        x = self.node_embedding(graphs.x) #CARE: is this ok? X seems to be simply stacked
        edges=graphs.edge_index
        edge_attr=graphs.edge_attr
        batch=graphs.batch

        x = self.conv1(x, edges, edge_attr)
        x = F.relu(x)
        x = self.conv2(x, edges, edge_attr)
        x = F.relu(x)
        x = self.conv3(x, edges, edge_attr)
        x = global_mean_pool(x, batch)  # [batch_size, hidden_channels]

        #x = self.W_g(x)

        #x=x/torch.norm(x, dim=1, keepdim=True)
        
        return x        

class VisualGraphEmbeddingAsymetric(torch.nn.Module):
    def __init__(self,image_model, embedding_dim):
        super(VisualGraphEmbeddingAsymetric, self).__init__()

        self.embedding_dim=embedding_dim

        #Graph layers
        self.conv1 = GCNConv(self.embedding_dim, self.embedding_dim)
        self.conv2 = GCNConv(self.embedding_dim, self.embedding_dim)
        self.conv3 = GCNConv(self.embedding_dim, self.embedding_dim)

        self.node_embedding=torch.nn.Embedding(30, self.embedding_dim) #30 should be enough
        self.node_embedding.requires_grad_(False) # Performance proved better w/o training the Embedding ✓

        #Image model
        self.image_model=image_model
        self.image_model.requires_grad_(False)
        self.image_model.eval()
        #self.image_dim=image_model.dim*image_model.num_clusters #Output gets flattened during NetVLAD
        self.image_dim=list(image_model.parameters())[-1].shape[0] #For VGG
        assert self.image_dim==4096        
        
        #Linear layers
        self.W_i=torch.nn.Linear(self.image_dim,self.embedding_dim,bias=True) #Only for the visual path
        self.W_combine=torch.nn.Linear(self.image_dim+self.embedding_dim,self.embedding_dim,bias=True) #Only for the visual-geometric path

    def forward(self, images, graphs):
        #assert len(graphs)==len(images)

        out_images=self.encode_images(images)
        out_images_with_graphs=self.encode_images_with_graphs(images, graphs)
        assert out_images.shape==out_images_with_graphs.shape

        return out_images, out_images_with_graphs
        
    #Purely visual path
    #Care: don't use this in asymetric path
    def encode_images(self, images):
        assert len(images.shape)==4 #Expect a batch of images
        x=self.image_model(images)
        x=self.W_i(x)
        x=x/torch.norm(x, dim=1, keepdim=True)

        return x

    #Visual-geometric path
    def encode_images_with_graphs(self, images, graphs):
        xg = self.node_embedding(graphs.x)
        
        edges=graphs.edge_index
        edge_attr=graphs.edge_attr
        batch=graphs.batch

        xg = self.conv1(xg, edges, edge_attr)
        xg = F.relu(xg)
        xg = self.conv2(xg, edges, edge_attr)
        xg = F.relu(xg)
        xg = self.conv3(xg, edges, edge_attr)
        xg = global_mean_pool(xg, batch)  # [batch_size, hidden_channels]

        xi=self.image_model(images)
        
        x=self.W_combine( torch.cat((xi, xg), dim=1) )
        x=x/torch.norm(x, dim=1, keepdim=True)
        
        return x                