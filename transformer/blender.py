import cv2
import numpy as np
import scipy.sparse

def mask_from_points(img, points):
  radius = 15  # kernel size
  kernel = np.ones((radius, radius), np.uint8)

  mask = np.zeros(img.shape[:2], np.uint8)
  cv2.fillConvexPoly(mask, cv2.convexHull(points), 255)
  mask = cv2.erode(mask, kernel)

  return mask

def alpha_feathering(dest_img, base_img, base_points):
  radius = 15  # kernel size
  kernel = np.ones((radius, radius), np.uint8)

  mask = np.zeros(base_img.shape[:2], np.uint8)
  cv2.fillConvexPoly(mask, cv2.convexHull(base_points), 255)
  mask = cv2.erode(mask, kernel)

  mask = cv2.blur(mask, (radius, radius))
  mask = mask / 255.0

  result_img = np.empty(base_img.shape, np.uint8)
  for i in xrange(3):
    result_img[..., i] = dest_img[..., i] * mask + base_img[..., i] * (1-mask)

  return result_img

def poission_blend(img_target, img_source, img_mask, offset=(0, 0)):
  import pyamg
  # compute regions to be blended
  region_source = (
    max(-offset[0], 0),
    max(-offset[1], 0),
    min(img_target.shape[0] - offset[0], img_source.shape[0]),
    min(img_target.shape[1] - offset[1], img_source.shape[1]))
  region_target = (
    max(offset[0], 0),
    max(offset[1], 0),
    min(img_target.shape[0], img_source.shape[0] + offset[0]),
    min(img_target.shape[1], img_source.shape[1] + offset[1]))
  region_size = (region_source[2] - region_source[0], region_source[3] - region_source[1])

  # clip and normalize mask image
  img_mask = img_mask[region_source[0]:region_source[2], region_source[1]:region_source[3]]

  # create coefficient matrix
  A = scipy.sparse.identity(np.prod(region_size), format='lil')
  for y in range(region_size[0]):
    for x in range(region_size[1]):
      if img_mask[y, x]:
        index = x + y * region_size[1]
        A[index, index] = 4
        if index + 1 < np.prod(region_size):
          A[index, index + 1] = -1
        if index - 1 >= 0:
          A[index, index - 1] = -1
        if index + region_size[1] < np.prod(region_size):
          A[index, index + region_size[1]] = -1
        if index - region_size[1] >= 0:
          A[index, index - region_size[1]] = -1
  A = A.tocsr()

  # create poisson matrix for b
  P = pyamg.gallery.poisson(img_mask.shape)
  # for each layer (ex. RGB)
  for num_layer in range(img_target.shape[2]):
    # get subimages
    t = img_target[region_target[0]:region_target[2], region_target[1]:region_target[3], num_layer]
    s = img_source[region_source[0]:region_source[2], region_source[1]:region_source[3], num_layer]
    t = t.flatten()
    s = s.flatten()

    # create b
    b = P * s
    for y in range(region_size[0]):
      for x in range(region_size[1]):
        if not img_mask[y, x]:
          index = x + y * region_size[1]
          b[index] = t[index]

    # solve Ax = b
    x = pyamg.solve(A, b, verb=False, tol=1e-10)

    # assign x to target image
    x = np.reshape(x, region_size)
    x[x > 255] = 255
    x[x < 0] = 0
    x = np.array(x, img_target.dtype)
    img_target[region_target[0]:region_target[2], region_target[1]:region_target[3], num_layer] = x

  return img_target