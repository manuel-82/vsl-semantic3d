import numpy as np
import os
import pptk
import time
import sys
import open3d
import capturing
import cv2
from semantic.imports import ClusteredObject
from graphics.imports import Pose, CLASSES_DICT, CLASSES_COLORS, COMBINED_SCENE_NAMES

import semantic.geometry
import semantic.utils
import pickle

'''
Module for testing 
'''

'''
TODO:
-what's up with the 2 colors mixed? -> many unlabeled points
-show L&Q -> done, Q approves
-render on SLURM-> not possible ✖
-possible to remove unlabeled near artifacts? -> yes, at least partly by kd-tree ✓ 
-load remaining training scenes -> Done on SLURM
-attempt NetVLAD on 200 pics, w/ and w/o label -> loss drops at least ✓

-compare quality full points at dense scene, w/ & w/o voxel-down
-clear up this file, mostly to rendering&graphics.utils
-Check Open3D outlier removal

-Check images in "Pictures" / take more
'''

# convert_txt('data/xyz_rgb/bildstein_station3_xyz_intensity_rgb.txt',
#             'data/labels/bildstein_station3_xyz_intensity_rgb.labels',
#             'data/numpy/bildstein_station3_xyz_intensity_rgb.xyz.npy',
#             'data/numpy/bildstein_station3_xyz_intensity_rgb.rgb.npy',
#             'data/numpy/bildstein_station3_xyz_intensity_rgb.labels.npy')

#DEPRECATED
def convert_txt(filepath_points, filepath_labels_in, filepath_xyz, filepath_rgb, filepath_labels_out):
    assert os.path.isfile(filepath_points)
    assert os.path.isfile(filepath_labels_in)
    assert not os.path.isfile(filepath_xyz)
    assert not os.path.isfile(filepath_rgb)
    assert not os.path.isfile(filepath_labels_out)

    print('\nloading points...')
    point_cloud=np.loadtxt(filepath_points, delimiter=' ', dtype=np.float32)
    num_points=point_cloud.shape[0]
    print(f'loading points done, {num_points} points')

    xyz=point_cloud[:,0:3]
    np.save(open(filepath_xyz,'wb'), xyz)
    xyz=None
    print('xyz saved.')

    rgb=point_cloud[:,4:].astype(np.uint8)
    np.save(open(filepath_rgb,'wb'), rgb)
    rgb=None
    print('rgb saved.')

    print('loading labels...')
    labels=np.loadtxt(filepath_labels_in, dtype=np.uint8).flatten()
    print('num labels:', labels.shape)
    np.save(open(filepath_labels_out, 'wb'), labels)
    labels=None
    print('labels saved')

    point_cloud=None

#Limit to 20M points
#Point treatment: Unknown points should be displayed in RGB-rendering for maximum texture-quality, but hidden in Label-rendering for clear label patches, artifacts should be expanded&hidden everywhere
def load_files(base_path, max_points=int(20e6), remove_artifacts=True, remove_unlabeled=True, expand_artifacts=True):
    p_xyz=base_path+'.xyz.npy'
    p_rgb=base_path+'.rgb.npy'
    p_labels=base_path+'.lbl.npy'

    assert os.path.isfile(p_xyz) and os.path.isfile(p_rgb) and os.path.isfile(p_labels)

    xyz, rgb, lbl=np.load(open(p_xyz,'rb')),np.load(open(p_rgb,'rb')),np.load(open(p_labels,'rb'))
    rgba= np.hstack((rgb, 255*np.ones((len(rgb),1))))
    rgb=None #Clear memory

    #Limit points
    step=int(np.ceil(len(xyz)/max_points))
    xyz,rgba,lbl= xyz[::step,:].copy(), rgba[::step,:].copy(), lbl[::step].copy()
    print(f'Limited points, step {step}, num-points: {len(xyz)}')

    # if halve_points:
    #     print('halving points CARE: QUARTER!')
    #     xyz, rgba, lbl= xyz[::4], rgba[::4], lbl[::4]

    
    #Iteratively expand the artifacts into unknowns
    k=5
    iterations=2
    if expand_artifacts:
        print(f"artefacts before: {np.sum(lbl==CLASSES_DICT['scanning artefacts'])/len(rgba):0.3f}")
        kd_tree=pptk.kdtree._build(xyz)
        for i in range(iterations):
            print('query tree...')
            neighbors=pptk.kdtree._query(kd_tree, lbl==CLASSES_DICT['scanning artefacts'], k=5) #Neighbors for every artifact point, kd-query returns absolute indices apparently
            neighbors=np.array(neighbors).flatten() #All neighbors of artifact points
            if len(neighbors)==0:
                break

            neighbors=neighbors[lbl[neighbors]==CLASSES_DICT['unlabeled']] #Neighbors of artefacts that are unknown
            lbl[neighbors]=CLASSES_DICT['scanning artefacts']
            neighbors=None
        print(f"artefacts after: {np.sum(lbl==CLASSES_DICT['scanning artefacts'])/len(rgba):0.3f}")

    labels_rgba=rgba.copy()
    for k in CLASSES_DICT.keys():
        mask= lbl==CLASSES_DICT[k]
        labels_rgba[mask,0:3]=CLASSES_COLORS[k]            

    #Hide artifacts in rgba and labels_rgba
    if remove_artifacts:
        mask= lbl==CLASSES_DICT['scanning artefacts']
        rgba[mask,3]=0
        labels_rgba[mask,3]=0
        print(f'hidden {np.sum(mask)/len(rgba):0.3f} artifacts (in rgba and labels_rgba)')

    #Hide unlabeled in labels_rgba
    if remove_unlabeled:
        mask = lbl==CLASSES_DICT['unlabeled']
        #rgba[mask,3]=0
        labels_rgba[mask,3]=0
        print(f'hidden {np.sum(mask)/len(rgba):0.3f} unlabeled (in labels_rgba)')

    return xyz, rgba, labels_rgba
    

def view_pptk(base_path, remove_artifacts=False, remove_unlabeled=True,max_points=None, return_xyz=False):
    if max_points is not None:
        xyz, rgba, labels_rgba=load_files(base_path, remove_artifacts=remove_artifacts, remove_unlabeled=remove_unlabeled, max_points=max_points)
    else:
        xyz, rgba, labels_rgba=load_files(base_path, remove_artifacts=remove_artifacts, remove_unlabeled=remove_unlabeled)

    viewer=pptk.viewer(xyz)
    viewer.attributes(rgba.astype(np.float32)/255.0,labels_rgba.astype(np.float32)/255.0)

    #viewer.color_map('hsv')
    viewer.set(point_size=0.025)

    if return_xyz:
        return viewer,xyz
    else:
        return viewer

# #PyVista bad for viewing?
# def view_pyvista(base_path, camera_pose):
#     xyz, rgba, labels_rgba=load_files(base_path,halve_points=True, remove_artifacts=True, remove_unlabeled=True)
#     mesh=pyvista.PolyData(xyz)
#     plotter=pyvista.Plotter()
#     plotter.add_mesh(mesh)
#     plotter.show(cpos=camera_pose, screenshot='testpose_vista.png')

#Deprecated?
def find_unlabeled_artifacts(xyz,lbl):
    unknown_labels=  lbl==classes_dict['unlabeled']   
    path_numpy='data/numpy/'
    path_results=os.path.join('data','pointcloud_images_o3d')
    artifact_labels= lbl==classes_dict['scanning artefacts']
    
    kd_tree=pptk.kdtree._build(xyz)    
    neighbour_indices=pptk.kdtree._query(kd_tree,unknown_labels,k=5) #query the K-NN indices for each unlabeled point
    neighbour_indices=np.array(neighbour_indices)

    neighbour_labels=np.take(lbl, neighbour_indices) # [N,k] array of the labels of the k neighbours each

def resize_window():
    os.system('wmctrl -r viewer -e 0,100,100,1620,1080')

#Diam größer -> weniger Punkte
if __name__ == "__main__":

    scene_name='bildstein_station1_xyz_intensity_rgb'
    viewer=view_pptk('data/numpy_merged/'+scene_name, remove_unlabeled=False, max_points=int(10e6))
    #poses_rendered=pickle.load( open('data/pointcloud_images_o3d_merged/bildstein_station1_xyz_intensity_rgb/poses_rendered.pkl','rb'))

    quit()

    scene_name='domfountain_station2_xyz_intensity_rgb'
    # xyz, rgba, labels_rgba=load_files('data/numpy/'+scene_name, remove_artifacts=True, remove_unlabeled=False, max_points=int(20e6))

    xyz=np.random.rand(100,3)

    pcd=open3d.geometry.PointCloud()
    pcd.points=open3d.utility.Vector3dVector(xyz)

    diam=0.001
    _, pt_map=pcd.hidden_point_removal([0,0,diam], 100*diam)
    print(len(pt_map))
    quit()

    vis = open3d.visualization.Visualizer()
    vis.create_window(width=1620, height=1080)
    vis.get_render_option().background_color = np.asarray([0, 0, 0])
    vis.add_geometry(pcd)
    vis.run()
 
    quit()


    viewer=view_pptk('data/numpy/'+scene_name,remove_artifacts=True, remove_unlabeled=False, max_points=int(5e6))
    resize_window()
    quit()


    # Sanity check: get_camera_matrices, project objects, draw objects
    scene_objects=pickle.load( open('data/numpy/'+scene_name+'.objects.pkl','rb'))
    viewer=view_pptk('data/numpy/'+scene_name,remove_artifacts=True, remove_unlabeled=False, max_points=int(5e6))
    resize_window()
    
    print('press to continue')
    _=input()
    pose = Pose(scene_name, viewer.get('eye'), viewer.get('right'), viewer.get('up'), viewer.get('view'))
    I,E=semantic.geometry.get_camera_matrices(pose)

    img=semantic.utils.viewer_to_image(viewer)
    for obj in scene_objects:
        obj.project(I,E)
        if semantic.geometry.is_object_in_fov(obj):
            obj.draw_on_image(img)

    cv2.imshow("",img); cv2.waitKey()
    cv2.imwrite("im.png",img)

    quit()
    

    #Automatic rendering
    if True:
        #for scene_name in ('domfountain_station1_xyz_intensity_rgb','sg27_station2_intensity_rgb','untermaederbrunnen_station1_xyz_intensity_rgb','neugasse_station1_xyz_intensity_rgb'):
        for scene_name in ('sg27_station2_intensity_rgb',):
            print('CAPTURING SCENE',scene_name)
            viewer, xyz=view_pptk('data/numpy/'+scene_name,remove_artifacts=True, remove_unlabeled=True,max_points=int(28e6), return_xyz=True) #int(28e6)
            base_path='data/pointcloud_images_3_2_depth/'+scene_name+'/'
            resize_window()
            time.sleep(2)

            #input('Enter to continue...')
            points=capturing.scene_config[scene_name]['points']
            point_size=capturing.scene_config[scene_name]['point_size_rgb']
            poses=capturing.points2poses(points,10)
            #capturing.capture_poses(viewer,base_path+'rgb',base_path+'lbl',base_path+'poses.npy',poses,point_size,2*point_size,num_angles=3, path_depth=base_path+'depth', xyz=xyz)
            capturing.capture_poses(viewer,out_filepath_poses=base_path+'poses.pkl', 
                                    poses=poses, 
                                    point_size_color=point_size, 
                                    point_size_labels=2*point_size, 
                                    path_rgb=base_path+'rgb',
                                    path_labels=base_path+'lbl',
                                    path_depth=base_path+'depth',
                                    xyz=xyz,
                                    num_angles=10)
            
            viewer.close()
        quit()

    # eye=np.array([-22.36111259,  40.53964615,  28.96756744])
    # lookat=np.array([-11.29156113,   9.60231495,   5.21776962])
    # up=np.array([ 0.19734934, -0.55155456,  0.81045717])


    #Open3D
    if False:
        xyz, rgba, labels_rgba=load_files('data/numpy/'+scene_name,remove_artifacts=True, remove_unlabeled=True, max_points=int(15e6))
        labels_rgba=None

        point_cloud=open3d.geometry.PointCloud()
        point_cloud.points=open3d.utility.Vector3dVector(xyz)
        point_cloud.colors=open3d.utility.Vector3dVector(rgba[:,0:3]/255.0)

        #open3d.visualization.draw_geometries([point_cloud])
        vis = open3d.visualization.Visualizer()
        vis.create_window(width=2160, height=2160)
        
        opt = vis.get_render_option()
        opt.background_color = np.asarray([0, 0, 0])

        vis.add_geometry(point_cloud)
        vis.run()
        vis.capture_screen_image('compare_o3d.jpg')
        vis.destroy_window()


        quit()

    # visualizer=open3d.visualization.Visualizer()
    # visualizer.create_window(width=1080, height=1080)
    # visualizer.add_geometry(point_cloud)
    # visualizer.update_geometry(point_cloud)
    # visualizer.poll_events()
    # visualizer.update_renderer()

    # controls=visualizer.get_view_control()
    # #visualizer.capture_screen_image('testpose_open3d.jpg')

    # quit()

    #PyVista rendering
    #view_pyvista('data/numpy/'+scene_name, [(-11.70296001,  27.92738342,  27.04918671), (-9.4, 8.265, 1.358), (0.09213677, -0.78672975,  0.6103828)])
    xyz, rgba, labels_rgba=load_files('data/numpy/'+scene_name,remove_artifacts=True, remove_unlabeled=True)
    labels_rgba=None
    rgb=rgba[:,0:3].copy() / 255.0
    rgba=None


    mesh=pyvista.PolyData(xyz)
    mesh['colors']=rgb


    #Smoothing
    #volume = mesh.delaunay_3d(alpha=17) #Takes too long

    plotter=pyvista.Plotter(window_size=[1920,2160], point_smoothing=False)
    plotter.add_mesh(mesh,scalars='colors', rgb=True)
    #CARE: pptk positions and PyVista positions don't match exactly!
    #res=plotter.show(cpos=[eye,lookat - eye,up],screenshot='testpose_vista_2.png', window_size=[1918,2029])

    res=plotter.show(window_size=[1920,2160])
    print(res)
    quit()


    #Automatic rendering
    # base_path='data/pointcloud_images/'+scene_name+'/'

    # input('Enter to continue...')
    # points=capturing.scene_config[scene_name]['points']
    # point_size=capturing.scene_config[scene_name]['point_size_rgb']
    # poses=capturing.points2poses(points,25)
    # capturing.capture_poses(viewer,base_path+'rgb',base_path+'lbl',base_path+'poses.npy',poses,point_size,2*point_size,8)


    #capturing.capture_poses(viewer,'t','rgb','lbl',poses[0:3],0.025,0.05,4)

    # base_name=sys.argv[1]
    # print('converting',base_name)
    # convert_txt(f'data/raw/{base_name}.txt',f'data/labels/{base_name}.labels',f'data/numpy/{base_name}.xyz.npy', f'data/numpy/{base_name}.rgb.npy', f'data/numpy/{base_name}.labels.npy')
    # print('done!\n\n')

    # print('loading pc...')
    # xyz=np.load(open('xyz_full.npy','rb'))
    # rgb=np.load(open('rgb_full.npy','rb'))
    # lbl=np.load(open('lbl_full.npy','rb'))

    # viewer=pptk.viewer(xyz,lbl)
    # viewer.attributes(rgb.astype(np.float32)/255.0)



    # Sem3d
    # -per image render from multiple locations with a full circle each
    # -retrieval based on SG&NetVLAD, localization based on NetVLAD
    # -possibly guide NetVLAD training w/ high-level semantics

    # -NetVLAD failures (vis. distinct objects ranked as similar)

    # Aachen
    # -check NetVLAD pairs (in dataset or Torstens github, Quinjie link)

    # for n in ('tc0_01', 'tc1_00', 'tc2_03'):
    #     img=cv2.imread(n+'_color.png')
    #     lbl=cv2.imread(n+'_label.png')
    #     i=np.hstack((img,lbl))
    #     cv2.imwrite(n+'.jpg',i)


    import numpy as np
    import pyvista
    plotter=pyvista.Plotter(off_screen=True, window_size=(1248,1248))
    xyz=np.random.rand(1000,3)*10
    color=np.zeros_like(xyz)
    color[:,0]=1.0

    mesh=pyvista.PolyData(xyz)
    mesh['colors']=color

    plotter.add_mesh(mesh,scalars='colors', rgb=True)
    plotter.show(screenshot='pyvista_color.png', window_size=[1080,1080])
