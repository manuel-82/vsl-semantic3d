import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader
from torchvision import transforms
import string
import random
import os
import numpy as np
import cv2
import psutil
import matplotlib.pyplot as plt
import sys

from retrieval import networks
from retrieval.netvlad import NetVLAD, EmbedNet
from retrieval.utils import get_split_indices
from dataloading.data_loading import Semantic3dDatasetIdTriplets

'''
TODO:
-basic Resnet18+NetVLAD -> loss doesn't drop much
-check feature-alikeness vs. Aachen/DeepLoc (norm w/ norms) -> ✖ can't confirm - possibly distorted by a/p alikeness
-enforce closest anchor -> ✓ Yes, seems to help. Before the was sometimes barely overlap.
-check for reasons the loss is not dropping -> Positive pairs to close
-overfit 200 images, evaluate top-k dists, train on more scenes ✓
-Train&eval 4 scenes 3:2 aspect no split and 3-1 split: ✓ scene-retrieval good, high 
-nächstes Mal r=0? -> Yes, bzw eh via Open3D ✓
-Splitting&near-enough positives: bigger fov, check point-size, enough overlap w/ 12 angles
-Find pairs via Open3D visible points -> ✖ doesn't work

-Redo splitting w/ disjoint trajectories, less locations, random angles
-calc. average location dist, compare: 
-Compare training w/ nearest vs. random positive-anchor
-bigger encoder (FCN-Resnet101), too big for my GPU
-ggf. train segmentation model (check avg p/n feature alikeness before/after)

-More training optimization: more epochs, shuffle, test-loss, acc. checks, ??

MODELS:
resnet18, 200 images            : ({1: 1.598, 5: 3.49, 10: 5.17}, {1: 0.0,   5: 0.361, 10: 0.416})
resnet18, 480i, 50-50 neg. idx  : ({1: 5.681, 5: 8.44, 10: 9.98}, {1: 0.701, 5: 0.955, 10: 1.087}, {1: 0.92, 5: 0.868, 10: 0.80})
resnet18, 480i, same scene neg. :

resnet18, 480i, 3:2 , no split  : ({1: 4.805, 5: 7.617, 10: 9.23}, {1: 0.2932, 5: 0.463, 10: 0.609}, {1: 1.0, 5: 0.964, 10: 0.95})
same, 3-1 split test->train ret.: ({1: 4.55, 5: 5.336, 10: 6.27}, {1: 1.184, 5: 1.171, 10: 1.283}, {1: 1.0, 5: 0.988, 10: 0.976}) -> CARE: Higher ori. error because the nearest ones are "taken"
same, random                    : ({1: 5.887, 5: 10.17, 10: 12.414}, {1: 0.4817, 5: 1.416, 10: 1.522}, {1: 0.34, 5: 0.288, 10: 0.276}) #CARE: random can be quite volatile

----New scenes----

resnet18, 9scenes, 3:2, 3-1 split:  {1: 6.707, 3: 13.47, 5: 15.86, 10: 17.86} {1: 0.4788, 3: 0.792, 5: 0.894, 10: 1.064} {1: 0.84, 3: 0.8467, 5: 0.81, 10: 0.733}
resnet18, 10scenes, 3:2, 3-1 split: {1: 7.094, 3: 10.68, 5: 12.875, 10: 16.17} {1: 0.489, 3: 0.748, 5: 0.8545, 10: 1.011} {1: 0.927, 3: 0.884, 5: 0.8374, 10: 0.773}

'''

IMAGE_LIMIT=3000
BATCH_SIZE=8
LR_GAMMA=0.75
NUM_CLUSTERS=8 #16 clusters has similar loss #TODO: compare retrieval score
ALPHA=10.0 #Higher Alpha leads to bigger loss (also worse retrieval?)
OVERLAP=0.2
MARGIN=0.5 #Before: m=1.0

#Capture arguments
LR=float(sys.argv[-1])

print(f'image limit: {IMAGE_LIMIT} bs: {BATCH_SIZE} lr gamma: {LR_GAMMA} clusters: {NUM_CLUSTERS} alpha: {ALPHA} margin: {MARGIN} overlap: {OVERLAP} lr: {LR}')

transform=transforms.Compose([
    #transforms.Resize((950,1000)),
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
])

data_set=Semantic3dDatasetIdTriplets('data/pointcloud_images_o3d_merged_occ','train', positive_overlap=OVERLAP, transform=transform, image_limit=IMAGE_LIMIT)
data_loader=DataLoader(data_set, batch_size=BATCH_SIZE, num_workers=2, pin_memory=True, shuffle=True) #Option: shuffle

loss_dict={}
best_loss=np.inf
best_model=None

#for lr in (2e-2,1e-2,7.5e-3):
for lr in (2e-2,):
    print('\n\nlr: ',lr)
    encoder=networks.get_encoder_resnet18()
    encoder.requires_grad_(False) #Don't train encoder
    netvlad_layer=NetVLAD(num_clusters=NUM_CLUSTERS, dim=512, alpha=ALPHA)

    model=EmbedNet(encoder, netvlad_layer).cuda()


    criterion=nn.TripletMarginLoss(margin=MARGIN)
    optimizer=optim.Adam(model.parameters(), lr=lr)    
    scheduler=optim.lr_scheduler.ExponentialLR(optimizer,LR_GAMMA)    

    loss_dict[lr]=[]
    for epoch in range(10):
        epoch_loss_sum=0.0
        for i_batch, batch in enumerate(data_loader):
            a,p,n=batch        
            
            optimizer.zero_grad()
            a_out=model(a.cuda())
            p_out=model(p.cuda())
            n_out=model(n.cuda())

            loss=criterion(a_out,p_out,n_out)
            loss.backward()
            optimizer.step()

            l=loss.cpu().detach().numpy()
            epoch_loss_sum+=l
            #print(f'\r epoch {epoch} loss {l}',end='')
        
        scheduler.step()

        epoch_avg_loss = epoch_loss_sum/(i_batch+1)
        print(f'epoch {epoch} final avg-loss {epoch_avg_loss}')
        loss_dict[lr].append(epoch_avg_loss)

    #Now using loss-avg of last epoch!
    if epoch_avg_loss<best_loss:
        best_loss=epoch_avg_loss
        best_model=model

print('\n----')           
model_name=f'model_netvlad_l{IMAGE_LIMIT}_b{BATCH_SIZE}_g{LR_GAMMA:0.2f}_c{NUM_CLUSTERS}_a{ALPHA}_m{MARGIN}_o{OVERLAP}_lr{LR}.pth'
print('Saving best model',model_name)
torch.save(best_model.state_dict(),model_name)

for k in loss_dict.keys():
    l=loss_dict[k]
    line, = plt.plot(l)
    line.set_label(k)
plt.gca().set_ylim(bottom=0.0) #Set the bottom to 0.0
plt.legend()
#plt.show()
plt.savefig(f'loss_netvlad_l{IMAGE_LIMIT}_b{BATCH_SIZE}_g{LR_GAMMA:0.2f}_c{NUM_CLUSTERS}_a{ALPHA}_m{MARGIN}_o{OVERLAP}_lr{LR}.png')    
