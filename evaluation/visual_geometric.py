import pickle
import numpy as np
import cv2
import os
import torch
import sys
#from torch.utils.data import DataLoader
from torchvision import transforms
import torchvision.models
import torch.nn as nn

from torch_geometric.data import DataLoader #Use the PyG DataLoader

from dataloading.data_loading import Semantic3dDataset
from retrieval import networks
from retrieval.netvlad import NetVLAD, EmbedNet

from semantic.imports import SceneGraph, SceneGraphObject, ViewObject
from semantic.scene_graph_cluster3d_scoring import score_sceneGraph_to_viewObjects_nnRels
# from evaluation.utils import evaluate_topK, generate_sanity_check_dataset
from evaluation.utils import reduce_topK, print_topK
import evaluation.utils

from visual_semantic.visual_semantic_embedding import VisualSemanticEmbedding

from geometric.graph_embedding import GraphEmbedding
from geometric.visual_graph_embedding import create_image_model_vgg11, VisualGraphEmbeddingNetVLAD, VisualGraphEmbedding, VisualGraphEmbeddingCombined, VisualGraphEmbeddingAsymetric
from dataloading.data_cambridge import CambridgeDataset

def gather_GE_vectors(dataloader_train, dataloader_test, model):
    #Gather all features
    print('Building GE vectors')
    embed_vectors_train, embed_vectors_test=torch.tensor([]).cuda(), torch.tensor([]).cuda()
    with torch.no_grad():
        for i_batch, batch in enumerate(dataloader_train):
            a=batch['graphs']
            a_out=model(a.to('cuda'))
            embed_vectors_train=torch.cat((embed_vectors_train,a_out))   
        for i_batch, batch in enumerate(dataloader_test):
            a=batch['graphs']
            a_out=model(a.to('cuda'))
            embed_vectors_test=torch.cat((embed_vectors_test,a_out))
    embed_vectors_train=embed_vectors_train.cpu().detach().numpy()
    embed_vectors_test=embed_vectors_test.cpu().detach().numpy() 
    embed_dim=embed_vectors_test.shape[1]

    pickle.dump((embed_vectors_train, embed_vectors_test), open(f'features_GE_e{embed_dim}.pkl','wb'))
    print('Saved GE-vectors')

def gather_VGE_UE_vectors(dataloader_train, dataloader_test, model):
    #Gather all features
    print('Building VGE-UE vectors')
    embed_vectors_visual_train, embed_vectors_graph_train=torch.tensor([]).cuda(), torch.tensor([]).cuda()
    embed_vectors_visual_test, embed_vectors_graph_test=torch.tensor([]).cuda(), torch.tensor([]).cuda()
    with torch.no_grad():
        for i_batch, batch in enumerate(dataloader_train):
            out_visual, out_graph=model(batch['images'].to('cuda'), batch['graphs'].to('cuda'))
            embed_vectors_visual_train=torch.cat((embed_vectors_visual_train, out_visual))
            embed_vectors_graph_train=torch.cat((embed_vectors_graph_train, out_graph))  
        for i_batch, batch in enumerate(dataloader_test):
            out_visual, out_graph=model(batch['images'].to('cuda'), batch['graphs'].to('cuda'))
            embed_vectors_visual_test=torch.cat((embed_vectors_visual_test, out_visual))
            embed_vectors_graph_test=torch.cat((embed_vectors_graph_test, out_graph))  
    embed_vectors_visual_train=embed_vectors_visual_train.cpu().detach().numpy()
    embed_vectors_graph_train =embed_vectors_graph_train.cpu().detach().numpy()
    embed_vectors_visual_test=embed_vectors_visual_test.cpu().detach().numpy()
    embed_vectors_graph_test =embed_vectors_graph_test.cpu().detach().numpy()    
    embed_dim=embed_vectors_graph_train.shape[1]

    assert len(embed_vectors_visual_train)==len(embed_vectors_graph_train)==len(dataloader_train.dataset)
    assert len(embed_vectors_visual_test)==len(embed_vectors_graph_test)==len(dataloader_test.dataset)

    pickle.dump((embed_vectors_visual_train, embed_vectors_graph_train, embed_vectors_visual_test, embed_vectors_graph_test), open(f'features_VGE-UE_e{embed_dim}.pkl','wb'))
    print('Saved VGE-UE_vectors')   

def gather_VGE_NV_vectors(dataloader_train, dataloader_test, model):
    #Gather all features
    print('Building VGE-NV vectors')
    embed_vectors_visual_train, embed_vectors_graph_train=torch.tensor([]).cuda(), torch.tensor([]).cuda()
    embed_vectors_visual_test, embed_vectors_graph_test=torch.tensor([]).cuda(), torch.tensor([]).cuda()
    with torch.no_grad():
        for i_batch, batch in enumerate(dataloader_train):
            out_visual, out_graph=model(batch['images'].to('cuda'), batch['graphs'].to('cuda'))
            embed_vectors_visual_train=torch.cat((embed_vectors_visual_train, out_visual))
            embed_vectors_graph_train=torch.cat((embed_vectors_graph_train, out_graph))  
        for i_batch, batch in enumerate(dataloader_test):
            out_visual, out_graph=model(batch['images'].to('cuda'), batch['graphs'].to('cuda'))
            embed_vectors_visual_test=torch.cat((embed_vectors_visual_test, out_visual))
            embed_vectors_graph_test=torch.cat((embed_vectors_graph_test, out_graph))  
    embed_vectors_visual_train=embed_vectors_visual_train.cpu().detach().numpy()
    embed_vectors_graph_train =embed_vectors_graph_train.cpu().detach().numpy()
    embed_vectors_visual_test=embed_vectors_visual_test.cpu().detach().numpy()
    embed_vectors_graph_test =embed_vectors_graph_test.cpu().detach().numpy()    
    embed_dim=embed_vectors_graph_train.shape[1]

    assert len(embed_vectors_visual_train)==len(embed_vectors_graph_train)==len(dataloader_train.dataset)
    assert len(embed_vectors_visual_test)==len(embed_vectors_graph_test)==len(dataloader_test.dataset)

    pickle.dump((embed_vectors_visual_train, embed_vectors_graph_train, embed_vectors_visual_test, embed_vectors_graph_test), open(f'features_VGE-NV_e{embed_dim}.pkl','wb'))
    print('Saved VGE-NV_vectors')    

def gather_VGE_NV_vectors_cambridge(dataloader_train, dataloader_test, model):
    #Gather all features
    print('Building VGE-NV vectors')
    embed_vectors_visual_train=torch.tensor([]).cuda()
    embed_vectors_visual_test=torch.tensor([]).cuda()
    with torch.no_grad():
        for i_batch, batch in enumerate(dataloader_train):
            out_visual=model.encode_images(batch.to('cuda'))
            embed_vectors_visual_train=torch.cat((embed_vectors_visual_train, out_visual)) 
        for i_batch, batch in enumerate(dataloader_test):
            out_visual=model.encode_images(batch.to('cuda'))
            embed_vectors_visual_test=torch.cat((embed_vectors_visual_test, out_visual))
    embed_vectors_visual_train=embed_vectors_visual_train.cpu().detach().numpy()
    embed_vectors_visual_test=embed_vectors_visual_test.cpu().detach().numpy()
    embed_dim=embed_vectors_visual_train.shape[1]

    assert len(embed_vectors_visual_train)==len(dataloader_train.dataset)
    assert len(embed_vectors_visual_test)==len(dataloader_test.dataset)

    #pickle.dump((embed_vectors_visual_train, embed_vectors_graph_train, embed_vectors_visual_test, embed_vectors_graph_test), open(f'features_VGE-UE_e{embed_dim}.pkl','wb'))
    #print('Saved VGE-UE_vectors')  
    return embed_vectors_visual_train, embed_vectors_visual_test     

def randomize_graphs(graph_batch):
    t=graph_batch.x.dtype
    graph_batch.x=torch.randint_like(graph_batch.x.type(torch.float), low=0, high=20).type(t)

    t=graph_batch.edge_attr.dtype
    graph_batch.edge_attr=torch.randint_like(graph_batch.edge_attr, low=0, high=4).type(t)

    edge_index_clone=graph_batch.edge_index.clone().detach()
    graph_batch.edge_index[0,:]=edge_index_clone[1,:]
    graph_batch.edge_index[1,:]=edge_index_clone[0,:]    
    return graph_batch

def gather_VGE_CO_vectors(dataloader_train, dataloader_test, model, use_random_graphs=False):
    #Gather all features
    print('Building VGE-CO vectors, random graphs:',use_random_graphs)
    embed_vectors_train, embed_vectors_test=torch.tensor([]).cuda(), torch.tensor([]).cuda()
    with torch.no_grad():
        for i_batch, batch in enumerate(dataloader_train):
            input_image, input_graphs=batch['images'], batch['graphs']
            if use_random_graphs: 
                input_graphs=randomize_graphs(input_graphs)

            out=model(input_image.to('cuda'), input_graphs.to('cuda'))
            embed_vectors_train=torch.cat((embed_vectors_train, out))
        for i_batch, batch in enumerate(dataloader_test):
            input_image, input_graphs=batch['images'], batch['graphs']
            if use_random_graphs: 
                input_graphs=randomize_graphs(input_graphs)
            
            out=model(input_image.to('cuda'), input_graphs.to('cuda'))
            embed_vectors_test=torch.cat((embed_vectors_test, out)) 

    embed_vectors_train=embed_vectors_train.cpu().detach().numpy()
    embed_vectors_test =embed_vectors_test.cpu().detach().numpy()
    embed_dim=embed_vectors_train.shape[1]

    assert len(embed_vectors_train)==len(dataloader_train.dataset)
    assert len(embed_vectors_test)==len(dataloader_test.dataset)

    pickle.dump((embed_vectors_train, embed_vectors_test), open(f'features_VGE-CO_e{embed_dim}_rg{use_random_graphs}.pkl','wb'))
    print('Saved VGE-CO_vectors')   

def gather_VGE_AS_vectors(dataloader_train, dataloader_test, model, use_random_graphs=False):
    #Gather all features
    print('Building VGE-AS vectors, random graphs:',use_random_graphs)
    embed_vectors_train, embed_vectors_test=torch.tensor([]).cuda(), torch.tensor([]).cuda()
    with torch.no_grad():
        #Encode via purely-visual path on training side
        for i_batch, batch in enumerate(dataloader_train):
            out=model.encode_images(batch['images'].to('cuda'))
            embed_vectors_train=torch.cat((embed_vectors_train, out))

        #Encode via combined visual-geometric path on testing side
        for i_batch, batch in enumerate(dataloader_test):
            input_image, input_graphs=batch['images'], batch['graphs']
            if use_random_graphs: 
                input_graphs=randomize_graphs(input_graphs)

            out=model.encode_images_with_graphs(input_image.to('cuda'), input_graphs.to('cuda'))
            embed_vectors_test=torch.cat((embed_vectors_test, out)) 

    embed_vectors_train=embed_vectors_train.cpu().detach().numpy()
    embed_vectors_test =embed_vectors_test.cpu().detach().numpy()
    embed_dim=embed_vectors_train.shape[1]

    assert len(embed_vectors_train)==len(dataloader_train.dataset)
    assert len(embed_vectors_test)==len(dataloader_test.dataset)

    pickle.dump((embed_vectors_train, embed_vectors_test), open(f'features_VGE-AS_e{embed_dim}_rg{use_random_graphs}.pkl','wb'))
    print('Saved VGE-AS_vectors')      

def gather_VGE_NV_ImageOnly_vectors(dataloader_train, dataloader_test, model):
    #Gather all features
    print('Building VGE-NV-ImageOnly vectors')
    embed_vectors_train, embed_vectors_test=torch.tensor([]).cuda(), torch.tensor([]).cuda()
    with torch.no_grad():
        for i_batch, batch in enumerate(dataloader_train):
            if type(batch)==dict: batch=batch['images'] #CARE: this ok?!
            out=model.encode_images(batch.cuda())
            embed_vectors_train=torch.cat((embed_vectors_train, out))
        for i_batch, batch in enumerate(dataloader_test):
            if type(batch)==dict: batch=batch['images']
            out=model.encode_images(batch.cuda())
            embed_vectors_test=torch.cat((embed_vectors_test, out)) 

    embed_vectors_train=embed_vectors_train.cpu().detach().numpy()
    embed_vectors_test =embed_vectors_test.cpu().detach().numpy()
    embed_dim=embed_vectors_train.shape[1]

    assert len(embed_vectors_train)==len(dataloader_train.dataset)
    assert len(embed_vectors_test)==len(dataloader_test.dataset)

    pickle.dump((embed_vectors_train, embed_vectors_test), open(f'features_VGE-NV-ImageOnly_e{embed_dim}.pkl','wb'))
    print('Saved VGE-NV-ImageOnly_vectors')   
    return embed_vectors_train, embed_vectors_test

'''
Goes from query-side embed-vectors to db-side embed vectors
Used for vectors from GE, VGE-UE and VGE-NV
'''
def eval_GE_scoring(dataset_train, dataset_test, embedding_train, embedding_test, similarity_measure, top_k=(1,3,5,10), thresholds=[(15.0,45), (25.0,60), (50.0,90)], reduce_indices=None):
    assert len(embedding_train)==len(dataset_train) and len(embedding_test)==len(dataset_test)
    assert similarity_measure in ('cosine','l2')
    assert reduce_indices in (None, 'scene-voting')
    print(f'eval_GE_scoring(): # training: {len(dataset_train)}, # test: {len(dataset_test)}')
    print('Similarity measure:',similarity_measure,'Reduce indices:',reduce_indices)    

    image_positions_train, image_orientations_train = dataset_train.image_positions, dataset_train.image_orientations
    image_positions_test, image_orientations_test = dataset_test.image_positions, dataset_test.image_orientations
    scene_names_train = dataset_train.image_scene_names
    scene_names_test  = dataset_test.image_scene_names    

    retrieval_dict={}

    # pos_results  ={k:[] for k in top_k}
    # ori_results  ={k:[] for k in top_k}
    # scene_results={k:[] for k in top_k}   

    thresh_hits  = {t: {k:[] for k in top_k} for t in thresholds }
    scene_hits   = {k:[] for k in top_k}    
    scene_counts = {k:[] for k in top_k}    

    test_indices=np.arange(len(dataset_test))    
    for test_index in test_indices:
        scene_name_gt=scene_names_test[test_index]
        train_indices=np.arange(len(dataset_train))

        if similarity_measure=='cosine':
            scores=embedding_train@embedding_test[test_index]
        if similarity_measure=='l2':
            scores= -1.0*np.linalg.norm( embedding_train-embedding_test[test_index], axis=1 )
        
        assert len(scores)==len(dataset_train)

        pos_dists=np.linalg.norm(image_positions_train[:]-image_positions_test[test_index], axis=1) #CARE: also adds z-distance
        ori_dists=np.abs(image_orientations_train[:]-image_orientations_test[test_index])
        ori_dists=np.minimum(ori_dists, 2*np.pi-ori_dists)

        #retrieval_dict[test_index]=sorted_indices[0:np.max(top_k)]

        for k in top_k:
            if reduce_indices is None:
                sorted_indices=np.argsort(-1.0*scores)[0:k] #High->Low
            if reduce_indices=='scene-voting':
                sorted_indices=np.argsort(-1.0*scores)[0:k] #High->Low
                sorted_indices=evaluation.utils.reduceIndices_sceneVoting(scene_names_train, sorted_indices)

            if k==np.max(top_k): retrieval_dict[test_index]=sorted_indices
            assert len(sorted_indices)<=k        

            scene_correct=np.array([scene_name_gt == scene_names_train[retrieved_index] for retrieved_index in sorted_indices[0:k]])
            topk_pos_dists=pos_dists[sorted_indices][scene_correct==True]
            topk_ori_dists=ori_dists[sorted_indices][scene_correct==True]

             #Count how many of the considered retrievals hit the correct scene
            scene_hits[k].append(np.sum(scene_correct))
            #Count how many retrievals were considered 
            scene_counts[k].append(len(scene_correct))
            assert scene_counts[k][-1]<=k

            #Count how many of the considered retrievals hit the thresholds
            if np.sum(scene_correct)>0:
                for t in thresholds:
                    absolute_pos_thresh=t[0]
                    absolute_ori_thresh=np.deg2rad(t[1])
                    thresh_hits[t][k].append( np.sum( (topk_pos_dists<=absolute_pos_thresh) & (topk_ori_dists<=absolute_ori_thresh) ) )
                    assert thresh_hits[t][k][-1] <= scene_hits[k][-1]

    for k in top_k:
        for t in thresholds:
            #Number of threshold hits over the number of considered retrievals (= number of scene-hits)
            thresh_hits[t][k]= np.sum(thresh_hits[t][k]) / np.sum(scene_counts[k])
        # Number of scene hits over the number of considered retrievals (all top-k)
        scene_hits[k]= np.sum(scene_hits[k]) / np.sum(scene_counts[k])

    return thresh_hits, scene_hits


'''
Different ways of combining the the NetVLAD retrievals and GE retrievals
-Summing up the NV- and GE-distances (care: weighting cos-similarity vs. L2-distance)
-Combining both retrievals -> scene voting -> NetVLAD
'''
def eval_netvlad_embeddingVectors(dataset_train, dataset_test, netvlad_train, netvlad_test, embedding_train, embedding_test ,top_k=(1,3,5,10), thresholds=[(15.0,45), (25.0,60), (50.0,90)], combine='distance-sum'):
    assert combine in ('distance-sum','scene-voting->netvlad')
    print('\n eval_netvlad_embeddingVectors():', combine)

    image_positions_train, image_orientations_train = dataset_train.image_positions, dataset_train.image_orientations
    image_positions_test, image_orientations_test = dataset_test.image_positions, dataset_test.image_orientations
    scene_names_train = dataset_train.image_scene_names
    scene_names_test  = dataset_test.image_scene_names   


    retrieval_dict={}

    # pos_results  ={k:[] for k in top_k}
    # ori_results  ={k:[] for k in top_k}
    # scene_results={k:[] for k in top_k}   

    thresh_hits  = {t: {k:[] for k in top_k} for t in thresholds }
    scene_hits   = {k:[] for k in top_k}    
    scene_counts = {k:[] for k in top_k}     

    test_indices=np.arange(len(dataset_test))    
    for test_index in test_indices:
        scene_name_gt=scene_names_test[test_index]
        train_indices=np.arange(len(dataset_train))

        netvlad_diffs  = np.linalg.norm( netvlad_train[:]  - netvlad_test[test_index] , axis=1 )
        scores=embedding_train@embedding_test[test_index]

        #Norm both for comparability
        netvlad_diffs = netvlad_diffs/np.max(np.abs(netvlad_diffs))
        scores= scores/np.max(np.abs(scores))
        assert len(netvlad_diffs)==len(scores)==len(dataset_train)

        pos_dists=np.linalg.norm(image_positions_train[:]-image_positions_test[test_index], axis=1) #CARE: also adds z-distance
        ori_dists=np.abs(image_orientations_train[:]-image_orientations_test[test_index])
        ori_dists=np.minimum(ori_dists, 2*np.pi-ori_dists)

        for k in top_k:
            if combine=='distance-sum': #TODO/CARE!
                combined_scores= scores + -1.0*netvlad_diffs 
                sorted_indices=np.argsort( -1.0*combined_scores)[0:k] #High->Low
            if combine=='scene-voting->netvlad':
                indices_netvlad=np.argsort(netvlad_diffs)[0:k] #Low->High
                indices_scenegraph=np.argsort(-1.0*scores)[0:k] #High->Low
                sorted_indices_netvlad,sorted_indices_ge=evaluation.utils.reduceIndices_sceneVoting(scene_names_train, indices_netvlad, indices_scenegraph)
                sorted_indices = sorted_indices_netvlad if len(sorted_indices_netvlad)>0 else sorted_indices_ge # Trust GE-indices if they are united enough to overrule NetVLAD, proved as best approach!

            if k==np.max(top_k): retrieval_dict[test_index]=sorted_indices  
            assert len(sorted_indices)<=k        

            scene_correct=np.array([scene_name_gt == scene_names_train[retrieved_index] for retrieved_index in sorted_indices[0:k]])
            topk_pos_dists=pos_dists[sorted_indices][scene_correct==True]
            topk_ori_dists=ori_dists[sorted_indices][scene_correct==True]                           

            #Count how many of the considered retrievals hit the correct scene
            scene_hits[k].append(np.sum(scene_correct))
            #Count how many retrievals were considered 
            scene_counts[k].append(len(scene_correct))
            assert scene_counts[k][-1]<=k

            #Count how many of the considered retrievals hit the thresholds
            if np.sum(scene_correct)>0:
                for t in thresholds:
                    absolute_pos_thresh=t[0]
                    absolute_ori_thresh=np.deg2rad(t[1])
                    thresh_hits[t][k].append( np.sum( (topk_pos_dists<=absolute_pos_thresh) & (topk_ori_dists<=absolute_ori_thresh) ) )
                    assert thresh_hits[t][k][-1] <= scene_hits[k][-1]

    for k in top_k:
        for t in thresholds:
            #Number of threshold hits over the number of considered retrievals (= number of scene-hits)
            thresh_hits[t][k]= np.sum(thresh_hits[t][k]) / np.sum(scene_counts[k])
        # Number of scene hits over the number of considered retrievals (all top-k)
        scene_hits[k]= np.sum(scene_hits[k]) / np.sum(scene_counts[k])

    return thresh_hits, scene_hits   

if __name__ == "__main__":
    IMAGE_LIMIT=3000
    BATCH_SIZE=6
    NUM_CLUSTERS=8
    EMBED_DIM=300
    ALPHA=10.0

    transform=transforms.Compose([
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
    ])  

    dataset_train=Semantic3dDataset('data/pointcloud_images_o3d_merged','train',transform=transform, image_limit=IMAGE_LIMIT, load_viewObjects=True, load_sceneGraphs=True, return_graph_data=True)
    dataset_test =Semantic3dDataset('data/pointcloud_images_o3d_merged','test', transform=transform, image_limit=IMAGE_LIMIT, load_viewObjects=True, load_sceneGraphs=True, return_graph_data=True)

    dataloader_train=DataLoader(dataset_train, batch_size=BATCH_SIZE, num_workers=2, pin_memory=True, shuffle=False) #CARE: put shuffle off
    dataloader_test =DataLoader(dataset_test , batch_size=BATCH_SIZE, num_workers=2, pin_memory=True, shuffle=False)           

    if 'gather-occ' in sys.argv:
        dataset_train=Semantic3dDataset('data/pointcloud_images_o3d_merged_occ','train',transform=transform, image_limit=IMAGE_LIMIT, load_viewObjects=True, load_sceneGraphs=True, return_graph_data=True)
        dataset_test =Semantic3dDataset('data/pointcloud_images_o3d_merged_occ','test', transform=transform, image_limit=IMAGE_LIMIT, load_viewObjects=True, load_sceneGraphs=True, return_graph_data=True)

        dataloader_train=DataLoader(dataset_train, batch_size=BATCH_SIZE, num_workers=2, pin_memory=True, shuffle=False) #CARE: put shuffle off
        dataloader_test =DataLoader(dataset_test , batch_size=BATCH_SIZE, num_workers=2, pin_memory=True, shuffle=False) 

        # #Gather Ge
        # EMBED_DIM_GEOMETRIC=100
        # geometric_embedding=GraphEmbedding(EMBED_DIM_GEOMETRIC)
        # geometric_embedding_model_name='model_GraphEmbed_l3000_dOCC_b12_g0.75_e100_sTrue_m0.5_lr0.0005.pth'
        # print('Model:',geometric_embedding_model_name)
        # geometric_embedding.load_state_dict(torch.load('models/'+geometric_embedding_model_name))
        # geometric_embedding.eval()
        # geometric_embedding.cuda()         
        # gather_GE_vectors(dataloader_train, dataloader_test, geometric_embedding)

        #GE-v2
        EMBED_DIM_GEOMETRIC=100
        geometric_embedding=GraphEmbedding(EMBED_DIM_GEOMETRIC)
        geometric_embedding_model_name='model_GraphEmbed-v2_l3000_dOCC_b12_g0.75_e100_sTrue_m0.5_lr0.0005_o0.5.pth'
        print('Model:',geometric_embedding_model_name)
        geometric_embedding.load_state_dict(torch.load('models/'+geometric_embedding_model_name))
        geometric_embedding.eval()
        geometric_embedding.cuda()         
        gather_GE_vectors(dataloader_train, dataloader_test, geometric_embedding)                  

        #VGE-CO-v2
        EMBED_DIM_GEOMETRIC=1024               
        vgg=create_image_model_vgg11()
        vge_co_model=VisualGraphEmbeddingCombined(vgg, EMBED_DIM_GEOMETRIC).cuda()
        vge_co_model_name='model_VGE-CO-v2_l3000_b12_g0.75_e1024_sTrue_m0.5_lr5e-05_o0.5.pth'
        vge_co_model.load_state_dict(torch.load('models/'+vge_co_model_name)); print('Model:',vge_co_model_name)
        vge_co_model.eval()
        vge_co_model.cuda()
        gather_VGE_CO_vectors(dataloader_train, dataloader_test, vge_co_model, use_random_graphs=False)               

    if 'gather-coref' in sys.argv:
        dataset_train=Semantic3dDataset('data/pointcloud_images_o3d_merged','train',transform=transform, image_limit=IMAGE_LIMIT, load_viewObjects=True, load_sceneGraphs=True, return_graph_data=True, use_coref_graphs=True)
        dataset_test =Semantic3dDataset('data/pointcloud_images_o3d_merged','test', transform=transform, image_limit=IMAGE_LIMIT, load_viewObjects=True, load_sceneGraphs=True, return_graph_data=True, use_coref_graphs=True)
        dataloader_train=DataLoader(dataset_train, batch_size=BATCH_SIZE, num_workers=2, pin_memory=True, shuffle=False) #CARE: put shuffle off
        dataloader_test =DataLoader(dataset_test , batch_size=BATCH_SIZE, num_workers=2, pin_memory=True, shuffle=False)          

        EMBED_DIM_GEOMETRIC=100
        geometric_embedding=GraphEmbedding(EMBED_DIM_GEOMETRIC)
        geometric_embedding_model_name='model_GraphEmbed_l3000_dBASE-COREF_b12_g0.75_e100_sTrue_m0.5_lr0.0005.pth'
        print('Model:',geometric_embedding_model_name)
        geometric_embedding.load_state_dict(torch.load('models/'+geometric_embedding_model_name))
        geometric_embedding.eval()
        geometric_embedding.cuda()         
        gather_GE_vectors(dataloader_train, dataloader_test, geometric_embedding)

        quit()  

    if 'gather' in sys.argv:
        # #Gather Ge
        # EMBED_DIM_GEOMETRIC=100
        # geometric_embedding=GraphEmbedding(EMBED_DIM_GEOMETRIC)
        # geometric_embedding_model_name='model_GraphEmbed_l3000_b12_g0.75_e100_sTrue_m0.5_lr0.0005.pth'
        # print('Model:',geometric_embedding_model_name)
        # geometric_embedding.load_state_dict(torch.load('models/'+geometric_embedding_model_name))
        # geometric_embedding.eval()
        # geometric_embedding.cuda()         
        # gather_GE_vectors(dataloader_train, dataloader_test, geometric_embedding)      

        # EMBED_DIM_GEOMETRIC=300
        # geometric_embedding=GraphEmbedding(EMBED_DIM_GEOMETRIC)
        # geometric_embedding_model_name='model_GraphEmbed_l3000_b12_g0.75_e300_sTrue_m0.5_lr0.001.pth'
        # print('Model:',geometric_embedding_model_name)
        # geometric_embedding.load_state_dict(torch.load('models/'+geometric_embedding_model_name))
        # geometric_embedding.eval()
        # geometric_embedding.cuda()         
        # gather_GE_vectors(dataloader_train, dataloader_test, geometric_embedding)                      

        # #Gather VGE-UE
        # EMBED_DIM_GEOMETRIC=1024
        # vgg=create_image_model_vgg11()
        # vge_ue_model=VisualGraphEmbedding(vgg, EMBED_DIM_GEOMETRIC).cuda()
        # vge_ue_model_name='model_VGE-UE_l3000_b8_g0.75_e1024_sTrue_m0.5_lr0.0001.pth'
        # vge_ue_model.load_state_dict(torch.load('models/'+vge_ue_model_name)); print('Model:',vge_ue_model_name)
        # vge_ue_model.eval()
        # vge_ue_model.cuda()
        # gather_VGE_UE_vectors(dataloader_train, dataloader_test, vge_ue_model)

        # #Gather VGE-NV
        # EMBED_DIM_GEOMETRIC=1024
        # netvlad_model_name='model_netvlad_l3000_b6_g0.75_c8_a10.0.mdl'
        # print('NetVLAD Model:',netvlad_model_name)
        # netvlad_model=torch.load('models/'+netvlad_model_name)

        # vge_nv_model=VisualGraphEmbeddingNetVLAD(netvlad_model, EMBED_DIM_GEOMETRIC)
        # vge_nv_model_name='model_VGE-NV_l3000_b8_g0.75_e1024_sTrue_m0.5_lr0.0001.pth'
        # vge_nv_model.load_state_dict(torch.load('models/'+vge_nv_model_name)); print('Model:',vge_nv_model_name)
        # vge_nv_model.eval()
        # vge_nv_model.cuda()
        # gather_VGE_NV_vectors(dataloader_train, dataloader_test, vge_nv_model) 

        # #Gather VGE-CO
        # EMBED_DIM_GEOMETRIC=1024               
        # vgg=create_image_model_vgg11()
        # vge_co_model=VisualGraphEmbeddingCombined(vgg, EMBED_DIM_GEOMETRIC).cuda()
        # vge_co_model_name='model_VGE-CO_l3000_b12_g0.75_e1024_sTrue_m0.5_lr5e-05.pth'
        # vge_co_model.load_state_dict(torch.load('models/'+vge_co_model_name)); print('Model:',vge_co_model_name)
        # vge_co_model.eval()
        # vge_co_model.cuda()
        # gather_VGE_CO_vectors(dataloader_train, dataloader_test, vge_co_model, use_random_graphs=False)

        # #Gather VGE-CO (random graphs)
        # EMBED_DIM_GEOMETRIC=1024               
        # vgg=create_image_model_vgg11()
        # vge_co_model=VisualGraphEmbeddingCombined(vgg, EMBED_DIM_GEOMETRIC).cuda()
        # vge_co_model_name='model_VGE-CO_l3000_b12_g0.75_e1024_sTrue_m0.5_lr5e-05.pth'
        # vge_co_model.load_state_dict(torch.load('models/'+vge_co_model_name)); print('Model:',vge_co_model_name)
        # vge_co_model.eval()
        # vge_co_model.cuda()
        # gather_VGE_CO_vectors(dataloader_train, dataloader_test, vge_co_model, use_random_graphs=True)         

        # Gather VGE-AS
        # EMBED_DIM_GEOMETRIC=1024               
        # vgg=create_image_model_vgg11()
        # vge_co_model=VisualGraphEmbeddingAsymetric(vgg, EMBED_DIM_GEOMETRIC).cuda()
        # vge_co_model_name='model_VGE-AS_l3000_b10_g0.75_e1024_sTrue_m0.5_lr5e-4.pth'
        # vge_co_model.load_state_dict(torch.load('models/'+vge_co_model_name)); print('Model:',vge_co_model_name)
        # vge_co_model.eval()
        # vge_co_model.cuda()
        # gather_VGE_AS_vectors(dataloader_train, dataloader_test, vge_co_model, use_random_graphs=False)   

        #Gather VGE-AS (random graphs)
        # EMBED_DIM_GEOMETRIC=1024               
        # vgg=create_image_model_vgg11()
        # vge_co_model=VisualGraphEmbeddingAsymetric(vgg, EMBED_DIM_GEOMETRIC).cuda()
        # vge_co_model_name='model_VGE-AS_l3000_b10_g0.75_e1024_sTrue_m0.5_lr5e-4.pth'
        # vge_co_model.load_state_dict(torch.load('models/'+vge_co_model_name)); print('Model:',vge_co_model_name)
        # vge_co_model.eval()
        # vge_co_model.cuda()
        # gather_VGE_AS_vectors(dataloader_train, dataloader_test, vge_co_model, use_random_graphs=True)                

        # # Gather VGE-NV-ImageOnly
        # EMBED_DIM_GEOMETRIC=1024
        # netvlad_model_name='model_netvlad_l3000_b6_g0.75_c8_a10.0.mdl'
        # print('NetVLAD Model:',netvlad_model_name)
        # netvlad_model=torch.load('models/'+netvlad_model_name)

        # vge_nv_model=VisualGraphEmbeddingNetVLAD(netvlad_model, EMBED_DIM_GEOMETRIC)
        # vge_nv_model_name='model_VGE-NV-ImageOnly_l3000_b8_g0.75_e1024_sTrue_m1.0_lr0.0001_PRL.pth'
        # vge_nv_model.load_state_dict(torch.load('models/'+vge_nv_model_name)); print('Model:',vge_nv_model_name)
        # vge_nv_model.eval()
        # vge_nv_model.cuda()
        # gather_VGE_NV_ImageOnly_vectors(dataloader_train, dataloader_test, vge_nv_model)         
        pass      


    if 'GE-match' in sys.argv:
        ge_vectors_filename='features_GE_e100.pkl'
        ge_vectors_train, ge_vectors_test=pickle.load(open('evaluation_res/'+ge_vectors_filename,'rb')); print('Using vectors',ge_vectors_filename)
        thresh_results, scene_results=eval_GE_scoring(dataset_train, dataset_test, ge_vectors_train, ge_vectors_test,'l2', reduce_indices=None)
        print_topK(thresh_results, scene_results)
        thresh_results, scene_results=eval_GE_scoring(dataset_train, dataset_test, ge_vectors_train, ge_vectors_test,'l2', reduce_indices='scene-voting')
        print_topK(thresh_results, scene_results) 

        ge_vectors_filename='features_GE-COREF_e100.pkl'
        ge_vectors_train, ge_vectors_test=pickle.load(open('evaluation_res/'+ge_vectors_filename,'rb')); print('Using vectors',ge_vectors_filename)
        thresh_results, scene_results=eval_GE_scoring(dataset_train, dataset_test, ge_vectors_train, ge_vectors_test,'l2', reduce_indices=None)
        print_topK(thresh_results, scene_results)    

        ge_vectors_filename='features_GE_e300.pkl'
        ge_vectors_train, ge_vectors_test=pickle.load(open('evaluation_res/'+ge_vectors_filename,'rb')); print('Using vectors',ge_vectors_filename)
        thresh_results, scene_results=eval_GE_scoring(dataset_train, dataset_test, ge_vectors_train, ge_vectors_test,'l2', reduce_indices=None)
        print_topK(thresh_results, scene_results)        

        ge_vectors_filename='features_GE-v2_o0.3_e100.pkl'
        ge_vectors_train, ge_vectors_test=pickle.load(open('evaluation_res/'+ge_vectors_filename,'rb')); print('Using vectors',ge_vectors_filename)
        thresh_results, scene_results=eval_GE_scoring(dataset_train, dataset_test, ge_vectors_train, ge_vectors_test,'l2', reduce_indices=None)
        print_topK(thresh_results, scene_results)                        

    if 'NetVLAD+GE-match' in sys.argv:
        netvlad_vectors_filename='features_netvlad-S3D.pkl'
        netvlad_vectors_train,netvlad_vectors_test=pickle.load(open('evaluation_res/'+netvlad_vectors_filename,'rb')); print('Using vectors:', netvlad_vectors_filename)

        ge_vectors_filename='features_GE_e100.pkl'
        ge_vectors_train, ge_vectors_test=pickle.load(open('evaluation_res/'+ge_vectors_filename,'rb')); print('Using vectors',ge_vectors_filename)        

        thresh_results, scene_results=eval_netvlad_embeddingVectors(dataset_train, dataset_test, netvlad_vectors_train, netvlad_vectors_test, ge_vectors_train, ge_vectors_test, combine='distance-sum')
        print_topK(thresh_results, scene_results)
        thresh_results, scene_results=eval_netvlad_embeddingVectors(dataset_train, dataset_test, netvlad_vectors_train, netvlad_vectors_test, ge_vectors_train, ge_vectors_test, combine='scene-voting->netvlad')
        print_topK(thresh_results, scene_results)

    if 'NV-S3D-v2+GE-v2-match' in sys.argv:
        #v2
        netvlad_vectors_filename='features_netvlad_Occ-Occ_m0.5_o0.3.pkl'
        netvlad_vectors_train,netvlad_vectors_test=pickle.load(open('evaluation_res/'+netvlad_vectors_filename,'rb')); print('Using vectors:', netvlad_vectors_filename)

        ge_vectors_filename='features_GE-v2_o0.3_e100.pkl'
        ge_vectors_train, ge_vectors_test=pickle.load(open('evaluation_res/'+ge_vectors_filename,'rb')); print('Using vectors',ge_vectors_filename)        

        thresh_results, scene_results=eval_netvlad_embeddingVectors(dataset_train, dataset_test, netvlad_vectors_train, netvlad_vectors_test, ge_vectors_train, ge_vectors_test ,top_k=(1,3,5,10), combine='distance-sum')
        print_topK(thresh_results, scene_results)
        thresh_results, scene_results=eval_netvlad_embeddingVectors(dataset_train, dataset_test, netvlad_vectors_train, netvlad_vectors_test, ge_vectors_train, ge_vectors_test ,top_k=(10,15,20), combine='distance-sum')
        print_topK(thresh_results, scene_results)
        print('\n---\n')
        thresh_results, scene_results=eval_netvlad_embeddingVectors(dataset_train, dataset_test, netvlad_vectors_train, netvlad_vectors_test, ge_vectors_train, ge_vectors_test ,top_k=(1,3,5,10), combine='scene-voting->netvlad')
        print_topK(thresh_results, scene_results) 
        thresh_results, scene_results=eval_netvlad_embeddingVectors(dataset_train, dataset_test, netvlad_vectors_train, netvlad_vectors_test, ge_vectors_train, ge_vectors_test ,top_k=(10,15,20), combine='scene-voting->netvlad')
        print_topK(thresh_results, scene_results)                

    if 'VGE-UE-match' in sys.argv:
        vge_vectors_filename='features_VGE-UE_e1024.pkl'
        vge_vectors_visual_train, vge_vectors_graph_train, vge_vectors_visual_test, vge_vectors_graph_test=pickle.load(open('evaluation_res/'+vge_vectors_filename,'rb')); print('Using vectors',vge_vectors_filename)        

        print('Eval VGE-UE image-image')
        thresh_results, scene_results=eval_GE_scoring(dataset_train, dataset_test, vge_vectors_visual_train, vge_vectors_visual_test, 'cosine')
        print_topK(thresh_results, scene_results)   

        print('Eval VGE-UE graph-graph')
        thresh_results, scene_results=eval_GE_scoring(dataset_train, dataset_test, vge_vectors_graph_train, vge_vectors_graph_test, 'cosine') 
        print_topK(thresh_results, scene_results)

        print('Eval VGE-UE graph-image')
        thresh_results, scene_results=eval_GE_scoring(dataset_train, dataset_test, vge_vectors_visual_train, vge_vectors_graph_test, 'cosine')
        print_topK(thresh_results, scene_results)

    if 'NetVLAD+VGE-UE-match' in sys.argv:
        netvlad_vectors_filename='features_netvlad-S3D.pkl'
        netvlad_vectors_train,netvlad_vectors_test=pickle.load(open('evaluation_res/'+netvlad_vectors_filename,'rb')); print('Using vectors:', netvlad_vectors_filename)

        vge_vectors_filename='features_VGE-UE_e1024.pkl'
        vge_vectors_visual_train, vge_vectors_graph_train, vge_vectors_visual_test, vge_vectors_graph_test=pickle.load(open('evaluation_res/'+vge_vectors_filename,'rb')); print('Using vectors',vge_vectors_filename)        

        print('Eval NetVLAD + VGE-UE (graph->image)')
        thresh_results, scene_results=eval_netvlad_embeddingVectors(dataset_train, dataset_test, netvlad_vectors_train, netvlad_vectors_test, vge_vectors_visual_train, vge_vectors_graph_test, combine='distance-sum')
        print_topK(thresh_results, scene_results)
        thresh_results, scene_results=eval_netvlad_embeddingVectors(dataset_train, dataset_test, netvlad_vectors_train, netvlad_vectors_test, vge_vectors_visual_train, vge_vectors_graph_test, combine='scene-voting->netvlad')
        print_topK(thresh_results, scene_results)         

    if 'VGE-NV-match' in sys.argv:
        vge_vectors_filename='features_VGE-NV_e1024.pkl'
        vge_vectors_visual_train, vge_vectors_graph_train, vge_vectors_visual_test, vge_vectors_graph_test=pickle.load(open('evaluation_res/'+vge_vectors_filename,'rb')); print('Using vectors',vge_vectors_filename)        

        print('Eval VGE-NV image-image')
        thresh_results, scene_results=eval_GE_scoring(dataset_train, dataset_test, vge_vectors_visual_train, vge_vectors_visual_test, 'cosine')
        print_topK(thresh_results, scene_results)       

        print('Eval VGE-NV graph-graph')
        thresh_results, scene_results=eval_GE_scoring(dataset_train, dataset_test, vge_vectors_graph_train, vge_vectors_graph_test,'cosine')
        print_topK(thresh_results, scene_results)

        print('Eval VGE-NV graph-image')
        thresh_results, scene_results=eval_GE_scoring(dataset_train, dataset_test, vge_vectors_visual_train, vge_vectors_graph_test,'cosine')
        print_topK(thresh_results, scene_results)  

    if 'VGE-NV-ImageOnly-match' in sys.argv:
        vge_vectors_filename='features_VGE-NV-ImageOnly_e1024_m1.0_PRL.pkl'
        features_train, features_test=pickle.load(open('evaluation_res/'+vge_vectors_filename,'rb')); print('Using vectors',vge_vectors_filename)        

        print('Eval VGE-NV image-image')
        thresh_results, scene_results=eval_GE_scoring(dataset_train, dataset_test, features_train, features_test, 'cosine')
        print_topK(thresh_results, scene_results)        

    if 'NetVLAD+VGE-NV-match' in sys.argv:
        netvlad_vectors_filename='features_netvlad-S3D.pkl'
        netvlad_vectors_train,netvlad_vectors_test=pickle.load(open('evaluation_res/'+netvlad_vectors_filename,'rb')); print('Using vectors:', netvlad_vectors_filename)

        vge_vectors_filename='features_VGE-NV_e1024.pkl'
        vge_vectors_visual_train, vge_vectors_graph_train, vge_vectors_visual_test, vge_vectors_graph_test=pickle.load(open('evaluation_res/'+vge_vectors_filename,'rb')); print('Using vectors',vge_vectors_filename)        

        print('Eval NetVLAD + VGE-NV (graph->image)')
        thresh_results, scene_results=eval_netvlad_embeddingVectors(dataset_train, dataset_test, netvlad_vectors_train, netvlad_vectors_test, vge_vectors_visual_train, vge_vectors_graph_test, combine='distance-sum')
        print_topK(thresh_results, scene_results)  
        thresh_results, scene_results=eval_netvlad_embeddingVectors(dataset_train, dataset_test, netvlad_vectors_train, netvlad_vectors_test, vge_vectors_visual_train, vge_vectors_graph_test, combine='scene-voting->netvlad')
        print_topK(thresh_results, scene_results)    

    if 'VGE-NV-match-cambridge' in sys.argv:
        print('Eval VGE-NV (trained on S3D) on Cambridge (image-image)')
        #Build dataset
        data_set_train_cambridge=CambridgeDataset('data_cambridge','train',transform=transform)
        data_set_test_cambridge =CambridgeDataset('data_cambridge','test', transform=transform)

        data_loader_train_cambridge=DataLoader(data_set_train_cambridge, batch_size=BATCH_SIZE, num_workers=2, pin_memory=True, shuffle=False) #CARE: put shuffle off
        data_loader_test_cambridge =DataLoader(data_set_test_cambridge , batch_size=BATCH_SIZE, num_workers=2, pin_memory=True, shuffle=False)           

        #Gather vectors
        EMBED_DIM_GEOMETRIC=1024
        netvlad_model_name='model_netvlad_l3000_b6_g0.75_c8_a10.0.mdl'
        print('NetVLAD Model:',netvlad_model_name)
        netvlad_model=torch.load('models/'+netvlad_model_name)

        vge_nv_model=VisualGraphEmbeddingNetVLAD(netvlad_model, EMBED_DIM_GEOMETRIC)
        vge_nv_model_name='model_VGE-NV_l3000_b8_g0.75_e1024_sTrue_m0.5_lr0.0001.pth'
        vge_nv_model.load_state_dict(torch.load('models/'+vge_nv_model_name)); print('Model:',vge_nv_model_name)
        vge_nv_model.eval()
        vge_nv_model.cuda()
        embed_vectors_train, embed_vectors_test=gather_VGE_NV_vectors_cambridge(data_loader_train_cambridge, data_loader_test_cambridge, vge_nv_model)           

        #Perform evaluation
        print('Eval VGE-NV image-image on Cambridge')
        thresh_results, scene_results=eval_GE_scoring(data_set_train_cambridge, data_set_test_cambridge, embed_vectors_train, embed_vectors_test, 'cosine' ,top_k=(1,3,5,10))
        print_topK(thresh_results, scene_results)       

    if 'VGE-CO-match' in sys.argv:
        vge_vectors_filename='features_VGE-CO_e1024.pkl'
        vge_vectors_train, vge_vectors_test=pickle.load(open('evaluation_res/'+vge_vectors_filename,'rb')); print('Using vectors',vge_vectors_filename)
        thresh_results, scene_results=eval_GE_scoring(dataset_train, dataset_test, vge_vectors_train, vge_vectors_test,'cosine', reduce_indices=None)
        print_topK(thresh_results, scene_results)  
        thresh_results, scene_results=eval_GE_scoring(dataset_train, dataset_test, vge_vectors_train, vge_vectors_test,'cosine', reduce_indices='scene-voting')
        print_topK(thresh_results, scene_results)  

        vge_vectors_filename='features_VGE-CO_e1024_rgTrue.pkl'
        vge_vectors_train, vge_vectors_test=pickle.load(open('evaluation_res/'+vge_vectors_filename,'rb')); print('Using vectors',vge_vectors_filename)
        thresh_results, scene_results=eval_GE_scoring(dataset_train, dataset_test, vge_vectors_train, vge_vectors_test,'cosine', reduce_indices=None)
        print_topK(thresh_results, scene_results)    

        vge_vectors_filename='features_VGE-CO-v2_o0.5_e1024_rgFalse.pkl'
        vge_vectors_train, vge_vectors_test=pickle.load(open('evaluation_res/'+vge_vectors_filename,'rb')); print('Using vectors',vge_vectors_filename)
        thresh_results, scene_results=eval_GE_scoring(dataset_train, dataset_test, vge_vectors_train, vge_vectors_test,'cosine', reduce_indices=None)
        print_topK(thresh_results, scene_results)                       

    if 'VGE-AS-match' in sys.argv:
        vge_vectors_filename='features_VGE-AS_e1024.pkl'
        vge_vectors_train, vge_vectors_test=pickle.load(open('evaluation_res/'+vge_vectors_filename,'rb')); print('Using vectors',vge_vectors_filename)
        thresh_results, scene_results=eval_GE_scoring(dataset_train, dataset_test, vge_vectors_train, vge_vectors_test,'cosine', reduce_indices=None)
        print_topK(thresh_results, scene_results)  
        thresh_results, scene_results=eval_GE_scoring(dataset_train, dataset_test, vge_vectors_train, vge_vectors_test,'cosine', reduce_indices='scene-voting')
        print_topK(thresh_results, scene_results)   

        #Trained normally, eval with random vectors
        vge_vectors_filename='features_VGE-AS_e1024_rgTrue.pkl'
        vge_vectors_train, vge_vectors_test=pickle.load(open('evaluation_res/'+vge_vectors_filename,'rb')); print('Using vectors',vge_vectors_filename)
        thresh_results, scene_results=eval_GE_scoring(dataset_train, dataset_test, vge_vectors_train, vge_vectors_test,'cosine', reduce_indices=None)
        print_topK(thresh_results, scene_results)    

        #Train & eval with empty graphs
        vge_vectors_filename='features_VGE-AS_e1024_EmptyGraphsTrainEval.pkl'
        vge_vectors_train, vge_vectors_test=pickle.load(open('evaluation_res/'+vge_vectors_filename,'rb')); print('Using vectors',vge_vectors_filename)
        thresh_results, scene_results=eval_GE_scoring(dataset_train, dataset_test, vge_vectors_train, vge_vectors_test,'cosine', reduce_indices=None)
        print_topK(thresh_results, scene_results)                       

    if 'VGE-NV-ImageOnly-match' in sys.argv:
        vge_vectors_filename='features_VGE-NV-ImageOnly_e1024_m1.0_PRL.pkl'
        vge_vectors_visual_train, vge_vectors_visual_test=pickle.load(open('evaluation_res/'+vge_vectors_filename,'rb')); print('Using vectors',vge_vectors_filename)        

        print('Eval VGE-NV image-image')
        thresh_results, scene_results=eval_GE_scoring(dataset_train, dataset_test, vge_vectors_visual_train, vge_vectors_visual_test, 'l2')
        print_topK(thresh_results, scene_results)

    if 'VGE-NV-ImageOnly-match-cambridge' in sys.argv:
        print('Eval VGE-NV-ImageOnly (trained on S3D) on Cambridge (image-image)')
        #Build dataset
        data_set_train_cambridge=CambridgeDataset('data_cambridge','train',transform=transform)
        data_set_test_cambridge =CambridgeDataset('data_cambridge','test', transform=transform)

        data_loader_train_cambridge=DataLoader(data_set_train_cambridge, batch_size=BATCH_SIZE, num_workers=2, pin_memory=True, shuffle=False) #CARE: put shuffle off
        data_loader_test_cambridge =DataLoader(data_set_test_cambridge , batch_size=BATCH_SIZE, num_workers=2, pin_memory=True, shuffle=False)           

        #Gather vectors
        EMBED_DIM_GEOMETRIC=1024
        netvlad_model_name='model_netvlad_l3000_b6_g0.75_c8_a10.0.mdl'
        print('NetVLAD Model:',netvlad_model_name)
        netvlad_model=torch.load('models/'+netvlad_model_name)

        vge_nv_model=VisualGraphEmbeddingNetVLAD(netvlad_model, EMBED_DIM_GEOMETRIC)
        vge_nv_model_name='model_VGE-NV-ImageOnly_l3000_b8_g0.75_e1024_sTrue_m1.0_lr0.0001_PRL.pth'
        vge_nv_model.load_state_dict(torch.load('models/'+vge_nv_model_name)); print('Model:',vge_nv_model_name)
        vge_nv_model.eval()
        vge_nv_model.cuda()
        embed_vectors_train, embed_vectors_test=gather_VGE_NV_ImageOnly_vectors(data_loader_train_cambridge, data_loader_test_cambridge, vge_nv_model)                                 

        #Perform evaluation
        print('Eval VGE-NV-ImageOnly image-image on Cambridge')
        thresh_results, scene_results=eval_GE_scoring(data_set_train_cambridge, data_set_test_cambridge, embed_vectors_train, embed_vectors_test, 'cosine' ,top_k=(1,3,5,10))
        print_topK(thresh_results, scene_results)  
                   

