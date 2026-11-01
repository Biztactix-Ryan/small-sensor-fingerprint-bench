// SPDX-License-Identifier: LGPL-2.1-or-later
// Dumps OpenCV's AKAZE nonlinear scale space for the C port to be checked
// against (compare_evolution.py). OpenCV does not expose the evolution, so
// this builds the pinned 4.4.0 AKAZE sources (ref/, see README.md) against the
// installed OpenCV's core and imgproc; build.sh builds it.
//
//   evolution_ref WIDTH HEIGHT IMAGES.raw OUT.bin
//
// IMAGES.raw holds 8-bit images back to back. For each, OUT.bin gets the
// levels of the scale space (Lt, Lsmooth before the detector frees it, Lx,
// Ly and Ldet) with their parameters and FED steps, then the keypoints and descriptors of
// a full detectAndCompute through the same sources, as cv::AKAZE does it
// (threshold 0.0002, other parameters default), so that the harness can be
// checked against the installed cv::AKAZE. All values little-endian.
#include <cstdio>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <string>
#include <vector>

#include "AKAZEFeatures.cpp"
#include "fed.cpp"
#include "nldiffusion_functions.cpp"

using namespace cv;

static void put_i(std::ofstream& f, int v) { f.write((const char*)&v, 4); }
static void put_f(std::ofstream& f, float v) { f.write((const char*)&v, 4); }
static void put_mat(std::ofstream& f, const Mat& m)
{
  CV_Assert(m.type() == CV_32F && m.isContinuous());
  f.write((const char*)m.ptr<float>(), m.total() * 4);
}

// create_nonlinear_scale_space() of AKAZEFeatures.cpp up to the detector
// response, keeping Lsmooth and the contrast factor
static float scale_space(const Mat& image, const AKAZEOptions& options,
                         const std::vector<std::vector<float> >& tsteps_evolution,
                         Pyramid& evolution)
{
  Mat img;
  prepareInputImage(image, img);

  int ksize = getGaussianKernelSize(options.soffset);
  GaussianBlur(img, evolution[0].Lsmooth, Size(ksize, ksize), options.soffset, options.soffset, BORDER_REPLICATE);
  evolution[0].Lsmooth.copyTo(evolution[0].Lt);

  Mat Lx, Ly, Lsmooth, Lflow, Lstep;
  GaussianBlur(img, Lsmooth, Size(5, 5), 1.0f, 1.0f, BORDER_REPLICATE);
  Scharr(Lsmooth, Lx, CV_32F, 1, 0, 1, 0, BORDER_DEFAULT);
  Scharr(Lsmooth, Ly, CV_32F, 0, 1, 1, 0, BORDER_DEFAULT);
  Lsmooth.release();
  float kcontrast = compute_kcontrast(Lx, Ly, options.kcontrast_percentile, options.kcontrast_nbins);
  const float kcontrast0 = kcontrast;

  for (size_t i = 1; i < evolution.size(); i++) {
    MEvolution &e = evolution[i];

    if (e.octave > evolution[i - 1].octave) {
      resize(evolution[i - 1].Lt, e.Lt, e.size, 0, 0, INTER_AREA);
      kcontrast *= 0.75f;
    }
    else {
      evolution[i - 1].Lt.copyTo(e.Lt);
    }

    GaussianBlur(e.Lt, e.Lsmooth, Size(5, 5), 1.0f, 1.0f, BORDER_REPLICATE);
    Scharr(e.Lsmooth, Lx, CV_32F, 1, 0, 1.0, 0, BORDER_DEFAULT);
    Scharr(e.Lsmooth, Ly, CV_32F, 0, 1, 1.0, 0, BORDER_DEFAULT);
    compute_diffusivity(Lx, Ly, Lflow, kcontrast, options.diffusivity);

    const std::vector<float> &tsteps = tsteps_evolution[i - 1];
    for (size_t j = 0; j < tsteps.size(); j++) {
      const float step_size = tsteps[j] * 0.5f;
      non_linear_diffusion_step(e.Lt, Lflow, Lstep, step_size);
      add(e.Lt, Lstep, e.Lt);
    }
  }
  return kcontrast0;
}

int main(int argc, char** argv)
{
  if (argc != 5) {
    fprintf(stderr, "usage: %s WIDTH HEIGHT IMAGES.raw OUT.bin\n", argv[0]);
    return 2;
  }
  const int w = atoi(argv[1]), h = atoi(argv[2]);
  std::ifstream in(argv[3], std::ios::binary);
  std::ofstream out(argv[4], std::ios::binary);
  std::vector<uchar> buf((size_t)w * h);
  int count = 0, mismatches = 0;

  while (in.read((char*)buf.data(), buf.size())) {
    Mat image(h, w, CV_8U, buf.data());

    AKAZEOptions options;  // as akaze.cpp sets them up for cv::AKAZE_create(0.0002)
    options.descriptor = AKAZE::DESCRIPTOR_MLDB;
    options.descriptor_channels = 3;
    options.descriptor_size = 0;
    options.img_width = w;
    options.img_height = h;
    options.dthreshold = 0.0002f;
    options.omax = 4;
    options.nsublevels = 4;
    options.diffusivity = KAZE::DIFF_PM_G2;

    AKAZEFeatures impl(options);
    Pyramid evolution = impl.evolution_;
    float kcontrast = scale_space(image, impl.options_, impl.tsteps_, evolution);

    std::vector<KeyPoint> kpts;
    Mat desc;
    impl.Create_Nonlinear_Scale_Space(image);
    // the copy above must give the same evolution as the original
    for (size_t i = 0; i < evolution.size(); i++)
      if (std::memcmp(evolution[i].Lt.ptr(), impl.evolution_[i].Lt.ptr(), evolution[i].Lt.total() * 4)) {
        fprintf(stderr, "image %d level %zu: Lt differs from AKAZEFeatures'\n", count, i);
        mismatches++;
      }
    impl.Feature_Detection(kpts);
    impl.Compute_Descriptors(kpts, desc);

    out.write("AKZE", 4);
    put_i(out, (int)evolution.size());
    put_f(out, kcontrast);
    for (size_t i = 0; i < evolution.size(); i++) {
      const MEvolution& e = evolution[i];
      put_i(out, e.size.width);
      put_i(out, e.size.height);
      put_i(out, e.octave);
      put_i(out, e.sublevel);
      put_i(out, e.sigma_size);
      put_i(out, e.border);
      put_f(out, e.esigma);
      put_f(out, e.etime);
      const std::vector<float> none;
      const std::vector<float>& tau = i ? impl.tsteps_[i - 1] : none;
      put_i(out, (int)tau.size());
      for (float t : tau)
        put_f(out, t);
      put_mat(out, e.Lt);
      put_mat(out, e.Lsmooth);
      // first derivatives and detector response, as the detector computed them
      put_mat(out, impl.evolution_[i].Lx);
      put_mat(out, impl.evolution_[i].Ly);
      put_mat(out, impl.evolution_[i].Ldet);
    }
    put_i(out, (int)kpts.size());
    put_i(out, desc.cols);
    for (size_t k = 0; k < kpts.size(); k++) {
      const KeyPoint& p = kpts[k];
      put_f(out, p.pt.x);
      put_f(out, p.pt.y);
      put_f(out, p.size);
      put_f(out, p.angle);
      put_f(out, p.response);
      put_i(out, p.octave);
      put_i(out, p.class_id);
      out.write((const char*)desc.ptr((int)k), desc.cols);
    }
    count++;
  }
  fprintf(stderr, "%d images\n", count);
  return mismatches ? 1 : 0;
}
