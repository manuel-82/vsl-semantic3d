import pickle
import numpy as np
import cv2
import os
import torch
import sys
from torch.utils.data import DataLoader
from torchvision import transforms

from dataloading.data_loading import Semantic3dDataset, Semantic3dDatasetTriplet
from retrieval.utils import get_split_indices
from retrieval import networks
from retrieval.netvlad import NetVLAD, EmbedNet

from semantic.imports import SceneGraph, SceneGraphObject, ViewObject
from semantic.scene_graph_cluster3d_scoring import score_sceneGraph_to_viewObjects_nnRels
from evaluation.utils import evaluate_topK, generate_sanity_check_dataset


'''
Module for evaluation
All results as {k: avg-distance-err, }, {k: avg-orientation-err }, {k: avg-scene-hit, } | distance&ori.-errors are reported among scene-hits
'''

'''
TODO:
-general & cleaner function to prepare results ✓
'''

'''
Matching SGs analytically to the View-Objects from 3D-Clustering

4 scenes, random                                : {1: 1.826, 5: 8.55, 10: 12.336} {1: 0.3015, 5: 1.085, 10: 1.426} {1: 0.2, 5: 0.248, 10: 0.26} CARE:Increasing because of more scene-hits?
4 scenes, scenegraph_for_view_cluster3d_7corners: {1: 8.52, 5: 10.16, 10: 10.72} {1: 0.867, 5: 1.057, 10: 1.1} {1: 0.6, 5: 0.532, 10: 0.524}

10 scenes, NN-rels:                             : {1: 46.25, 3: 40.9, 5: 42.62, 10: 46.0} {1: 1.009, 3: 1.205, 5: 1.239, 10: 1.442} {1: 0.33, 3: 0.3132, 5: 0.3, 10: 0.288}

-simple check close-by / far away
-check top-hits
-Handle empty Scene Graphs (0.0 score ✓)
'''
def scenegraph_to_viewObjects(data_loader_train, data_loader_test, top_k=(1,3,5,10)):
    CHECK_COUNT=100
    print(f'# training: {len(data_loader_train.dataset)}, # test: {len(data_loader_test.dataset)}')

    retrieval_dict={}

    dataset_train=data_loader_train.dataset
    dataset_test=data_loader_test.dataset

    image_positions_train, image_orientations_train = data_loader_train.dataset.image_positions, data_loader_train.dataset.image_orientations
    image_positions_test, image_orientations_test = data_loader_test.dataset.image_positions, data_loader_test.dataset.image_orientations
    scene_names_train = data_loader_train.dataset.image_scene_names
    scene_names_test  = data_loader_test.dataset.image_scene_names

    pos_results  ={k:[] for k in top_k}
    ori_results  ={k:[] for k in top_k}
    scene_results={k:[] for k in top_k}

    if CHECK_COUNT==len(data_loader_test.dataset):
        print('evaluating all indices...')
        check_indices=np.arange(len(data_loader_test.dataset))
    else:
        print('evaluating random indices...')
        check_indices=np.random.randint(len(data_loader_test.dataset), size=CHECK_COUNT)

    for i_idx,idx in enumerate(check_indices):
        print(f'\r index {i_idx} of {CHECK_COUNT}', end='')
        scene_name_gt=scene_names_test[idx]

        #Score query SG vs. database scenes
        scene_graph=dataset_test.view_scenegraphs[idx]
        scores=np.zeros(len(dataset_train))
        for i in range(len(dataset_train)):
            score,_=score_sceneGraph_to_viewObjects_nnRels(scene_graph, dataset_train.view_objects[i])
            scores[i]=score
        #scores=np.random.rand(len(dataset))
        
        sorted_indices=np.argsort(-1.0*scores) #Sort highest -> lowest scores
        pos_dists=np.linalg.norm(image_positions_train[:]-image_positions_test[idx], axis=1) #CARE: also adds z-distance
        ori_dists=np.abs(image_orientations_train[:]-image_orientations_test[idx])
        ori_dists=np.minimum(ori_dists, 2*np.pi-ori_dists)

        retrieval_dict[idx]=sorted_indices[0:np.max(top_k)]

        for k in top_k:
            scene_correct=np.array([scene_name_gt == scene_names_train[retrieved_index] for retrieved_index in sorted_indices[0:k]])
            topk_pos_dists=pos_dists[sorted_indices[0:k]]
            topk_ori_dists=ori_dists[sorted_indices[0:k]]    

            #Append the average pos&ori. errors *for the cases that the scene was hit*
            pos_results[k].append( np.mean( topk_pos_dists[scene_correct==True]) if np.sum(scene_correct)>0 else None )
            ori_results[k].append( np.mean( topk_ori_dists[scene_correct==True]) if np.sum(scene_correct)>0 else None )
            scene_results[k].append( np.mean(scene_correct) ) #Always append the scene-scores
    
    assert len(pos_results[k])==len(ori_results[k])==len(scene_results[k])==CHECK_COUNT

    print('Saving retrieval results...')
    pickle.dump(retrieval_dict, open('retrievals_PureSG.pkl','wb'))

    return evaluate_topK(pos_results, ori_results, scene_results)

'''
Evaluating pure NetVLAD retrieval
'''
#TODO: Drop: scene names YES THIS ONE, training-pairs, eval-func ✖, check-indices ✖, other model
def netvlad_retrieval(data_loader_train, data_loader_test, model, top_k=(1,3,5,10), random_features=False):
    CHECK_COUNT=len(data_loader_test.dataset)
    print(f'# training: {len(data_loader_train.dataset)}, # test: {len(data_loader_test.dataset)}')

    retrieval_dict={}

    if random_features:
        print('Using random vectors (sanity check)')
        netvlad_vectors_train=np.random.rand(len(data_loader_train.dataset),2)
        netvlad_vectors_test=np.random.rand(len(data_loader_test.dataset),2)        
    else:
        print('Building NetVLAD vectors...')
        netvlad_vectors_train, netvlad_vectors_test=torch.tensor([]).cuda(), torch.tensor([]).cuda()

        with torch.no_grad():
            for i_batch, batch in enumerate(data_loader_test):
                a=batch
                a_out=model(a.cuda())
                netvlad_vectors_test=torch.cat((netvlad_vectors_test,a_out))
            for i_batch, batch in enumerate(data_loader_train):
                a=batch
                a_out=model(a.cuda())
                netvlad_vectors_train=torch.cat((netvlad_vectors_train,a_out))        

        netvlad_vectors_train=netvlad_vectors_train.cpu().detach().numpy()
        netvlad_vectors_test=netvlad_vectors_test.cpu().detach().numpy()

    image_positions_train, image_orientations_train = data_loader_train.dataset.image_positions, data_loader_train.dataset.image_orientations
    image_positions_test, image_orientations_test = data_loader_test.dataset.image_positions, data_loader_test.dataset.image_orientations
    scene_names_train = data_loader_train.dataset.image_scene_names
    scene_names_test  = data_loader_test.dataset.image_scene_names

    #Sanity check
    #netvlad_vectors_train, netvlad_vectors_test, image_positions_train, image_positions_test, image_orientations_train, image_orientations_test, scene_names_train, scene_names_test=generate_sanity_check_dataset()

    pos_results  ={k:[] for k in top_k}
    ori_results  ={k:[] for k in top_k}
    scene_results={k:[] for k in top_k}

    if CHECK_COUNT==len(data_loader_test.dataset):
        print('evaluating all indices...')
        check_indices=np.arange(len(netvlad_vectors_test))
    else:
        print('evaluating random indices...')
        check_indices=np.random.randint(len(netvlad_vectors_test), size=CHECK_COUNT)
        
    for idx in check_indices:
        scene_name_gt=scene_names_test[idx]

        netvlad_diffs=netvlad_vectors_train-netvlad_vectors_test[idx]
        netvlad_diffs=np.linalg.norm(netvlad_diffs,axis=1)   

        sorted_indices=np.argsort(netvlad_diffs) 
        pos_dists=np.linalg.norm(image_positions_train[:]-image_positions_test[idx], axis=1) #CARE: also adds z-distance
        ori_dists=np.abs(image_orientations_train[:]-image_orientations_test[idx])
        ori_dists=np.minimum(ori_dists, 2*np.pi-ori_dists)

        retrieval_dict[idx]=sorted_indices[0:np.max(top_k)]

        for k in top_k:
            #scene_correct=np.array([scene_name_gt == data_loader_train.dataset.get_scene_name(retrieved_index) for retrieved_index in sorted_indices[0:k]])
            scene_correct=np.array([scene_name_gt == scene_names_train[retrieved_index] for retrieved_index in sorted_indices[0:k]])
            topk_pos_dists=pos_dists[sorted_indices[0:k]]
            topk_ori_dists=ori_dists[sorted_indices[0:k]]    

            #Append the average pos&ori. errors *for the cases that the scene was hit*
            pos_results[k].append( np.mean( topk_pos_dists[scene_correct==True]) if np.sum(scene_correct)>0 else None )
            ori_results[k].append( np.mean( topk_ori_dists[scene_correct==True]) if np.sum(scene_correct)>0 else None )
            scene_results[k].append( np.mean(scene_correct) ) #Always append the scene-scores
    
    assert len(pos_results[k])==len(ori_results[k])==len(scene_results[k])==CHECK_COUNT

    print('Saving retrieval results...')
    pickle.dump(retrieval_dict, open('retrievals_NetVLAD.pkl','wb'))

    return evaluate_topK(pos_results, ori_results, scene_results)

#TODO: save retrieval indices for failure evaluation
if __name__ == "__main__":
    IMAGE_LIMIT=3000
    BATCH_SIZE=6
    NUM_CLUSTERS=8
    TEST_SPLIT=4
    ALPHA=10.0
    transform=transforms.Compose([
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
    ])  

    train_indices, test_indices=get_split_indices(TEST_SPLIT, 3000)
    data_set_train=Semantic3dDataset('data/pointcloud_images_o3d_merged', transform=transform, image_limit=IMAGE_LIMIT, split_indices=train_indices, load_viewObjects=True, load_sceneGraphs=True)
    data_set_test =Semantic3dDataset('data/pointcloud_images_o3d_merged', transform=transform, image_limit=IMAGE_LIMIT, split_indices=test_indices, load_viewObjects=True, load_sceneGraphs=True)

    data_loader_train=DataLoader(data_set_train, batch_size=BATCH_SIZE, num_workers=2, pin_memory=True, shuffle=False) #CARE: put shuffle off
    data_loader_test =DataLoader(data_set_test , batch_size=BATCH_SIZE, num_workers=2, pin_memory=True, shuffle=False)

    # for idx in range(len(data_set_train)):
    #     if data_set_train.get_scene_name(idx)!=data_set_train.image_scene_names[idx]:
    #         print(idx)

    # for idx in range(len(data_set_test)):
    #     if data_set_test.get_scene_name(idx)!=data_set_test.image_scene_names[idx]:
    #         print(idx)            

    '''
    Evaluation: NetVLAD retrieval
    '''
    if "netvlad" in sys.argv:
        #CARE: make sure options match model!
        print('## Evaluation: NetVLAD retrieval')
        encoder=networks.get_encoder_resnet18()
        encoder.requires_grad_(False) #Don't train encoder
        netvlad_layer=NetVLAD(num_clusters=NUM_CLUSTERS, dim=512, alpha=ALPHA)
        model=EmbedNet(encoder, netvlad_layer)

        model_name='model_l2800_b6_g0.75_c8_a10.0_split4.pth'
        model.load_state_dict(torch.load('models/'+model_name))
        model.eval()
        model.cuda()

        pos_results, ori_results, scene_results=netvlad_retrieval(data_loader_train, data_loader_test, model)
        print(pos_results, ori_results, scene_results)

    '''
    Evaluation: pure Scene Graph scoring
    '''
    if "scenegraphs" in sys.argv:
        print('## Evaluation: pure Scene Graph scoring')  
        pos_results, ori_results, scene_results=scenegraph_to_viewObjects(data_loader_train, data_loader_test)
        print(pos_results, ori_results, scene_results)        


#DEPRECATED
# def scenegraph_to_patches(base_path, top_k=(1,5,10)):
#     check_count=50

#     dataset=Semantic3dDataset(base_path)

#     distance_sum={ k:0 for k in top_k }
#     orientation_sum={ k:0 for k in top_k }
#     scene_sum={ k:0 for k in top_k }    

#     for check_idx in range(check_count):
#         #Score SG vs. all images
#         grounding_scores=np.zeros(len(dataset))
#         for i in range(len(dataset)):
#             score,_ = ground_scenegraph_to_patches( dataset.image_scenegraphs[i], dataset.image_patches[i] )
#             grounding_scores[i]=score
#         grounding_scores[check_idx]=0.0 #Don't score vs. self

#         sorted_indices=np.argsort( -1.0*grounding_scores) #Sort highest -> lowest scores

#         location_dists=dataset.image_poses[:,0:3]-dataset.image_poses[check_idx,0:3]
#         location_dists=np.linalg.norm(location_dists,axis=1)      

#         orientation_dists=np.abs(dataset.image_poses[:,3]-dataset.image_poses[check_idx,3]) 
#         orientation_dists=np.minimum(orientation_dists,2*np.pi-orientation_dists)          

#         scene_name_gt=dataset.get_scene_name(check_idx)

#         for k in top_k:
#             scene_correct= np.array([scene_name_gt == dataset.get_scene_name(retrieved_index) for retrieved_index in sorted_indices[0:k] ])
#             topk_loc_dists=location_dists[sorted_indices[0:k]]
#             topk_ori_dists=orientation_dists[sorted_indices[0:k]]

#             if np.sum(scene_correct)>0:
#                 distance_sum[k]   +=np.mean( topk_loc_dists[scene_correct==True] )
#                 orientation_sum[k]+=np.mean( topk_ori_dists[scene_correct==True] )
#                 scene_sum[k]      +=np.mean(scene_correct)            

#     distance_avg, orientation_avg, scene_avg={},{},{}
#     for k in top_k:
#         distance_avg[k] = distance_sum[k]/check_count
#         orientation_avg[k] = orientation_sum[k]/check_count
#         scene_avg[k]= scene_sum[k]/check_count
#         distance_avg[k],orientation_avg[k], scene_avg[k]=np.float16(distance_avg[k]),np.float16(orientation_avg[k]),np.float16(scene_avg[k]) #Make numbers more readable    

#     return distance_avg, orientation_avg, scene_avg
