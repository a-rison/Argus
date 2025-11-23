# ---------- Stage 1: Build OpenCV with CUDA ----------
FROM nvidia/cuda:12.6.2-cudnn-devel-ubuntu22.04 AS builder

ARG DEBIAN_FRONTEND=noninteractive
ARG CUDA_ARCH_BIN="8.6"

RUN rm -rf /var/lib/apt/lists/* \
 && apt-get update && apt-get upgrade -y \
 && apt-get install -y --no-install-recommends \
    build-essential cmake g++ wget unzip git pkg-config curl \
    python3.10 python3.10-dev python3-pip python3-numpy \
    libgl1-mesa-glx libglib2.0-0 libusb-1.0-0 \
    libgtk2.0-dev \
    libavcodec-dev libavformat-dev libswscale-dev \
    libtbb-dev libdc1394-dev libv4l-dev \
    libgstreamer1.0-dev libgstreamer-plugins-base1.0-dev \
 && python3.10 -m pip install --upgrade pip \
 && rm -rf /var/lib/apt/lists/*

# (Optional) plugin bundles for test builds; not required if you don't test here
RUN apt-get update && apt-get install -y --no-install-recommends \
      gstreamer1.0-plugins-base gstreamer1.0-plugins-good \
      gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly \
      gstreamer1.0-libav \
 && rm -rf /var/lib/apt/lists/*

ENV OPENCV_BUILD_DIR=/opt/opencv_build
WORKDIR ${OPENCV_BUILD_DIR}

RUN wget -O opencv.zip https://github.com/opencv/opencv/archive/refs/tags/4.10.0.zip \
 && wget -O opencv_contrib.zip https://github.com/opencv/opencv_contrib/archive/refs/tags/4.10.0.zip \
 && unzip -q opencv.zip && unzip -q opencv_contrib.zip

WORKDIR ${OPENCV_BUILD_DIR}/opencv-4.10.0/build

# TIP to slim more: add -D BUILD_LIST=core,imgproc,highgui,videoio,cudaimgproc,cudaarithm,dnn (only what you use)
RUN PY3_EXEC=/usr/bin/python3.10 && \
    PY3_PACK="$(python3.10 -c 'import site; print(site.getsitepackages()[0])')" && \
    cmake \
      -D CMAKE_BUILD_TYPE=Release \
      -D CMAKE_INSTALL_PREFIX=/usr/local \
      -D OPENCV_EXTRA_MODULES_PATH=../../opencv_contrib-4.10.0/modules \
      -D OPENCV_ENABLE_NONFREE=ON \
      -D OPENCV_GENERATE_PKGCONFIG=ON \
      -D OPENCV_PC_FILE_NAME=opencv.pc \
      -D WITH_CUDA=ON \
      -D WITH_CUDNN=ON \
      -D OPENCV_DNN_CUDA=ON \
      -D WITH_CUBLAS=ON \
      -D ENABLE_FAST_MATH=1 \
      -D CUDA_FAST_MATH=1 \
      -D CUDA_ARCH_BIN="${CUDA_ARCH_BIN}" \
      -D CUDA_TOOLKIT_ROOT_DIR=/usr/local/cuda \
      -D WITH_TBB=ON \
      -D WITH_V4L=ON \
      -D WITH_QT=OFF \
      -D WITH_OPENGL=OFF \
      -D WITH_GSTREAMER=ON \
      -D BUILD_opencv_cudacodec=OFF \
      -D BUILD_opencv_apps=OFF \
      -D BUILD_opencv_python2=OFF \
      -D BUILD_opencv_python3=ON \
      -D PYTHON3_EXECUTABLE="${PY3_EXEC}" \
      -D PYTHON3_PACKAGES_PATH="${PY3_PACK}" \
      -D BUILD_TESTS=OFF \
      -D BUILD_PERF_TESTS=OFF \
      -D BUILD_EXAMPLES=OFF \
      -D INSTALL_PYTHON_EXAMPLES=OFF \
      -D INSTALL_C_EXAMPLES=OFF \
      ..

RUN make -j"$(nproc)" && make install && ldconfig && \
    find /usr/local -type f -name "*.a" -delete && \
    find /usr/local -type f -name "*.la" -delete && \
    find /usr/local/lib -type f -name "*.so*" -exec strip --strip-unneeded {} + || true

# ---------- Stage 2: Runtime ----------
FROM nvidia/cuda:12.6.2-cudnn-runtime-ubuntu22.04 AS runtime
ARG DEBIAN_FRONTEND=noninteractive
ENV PIP_NO_CACHE_DIR=1 PYTHONUNBUFFERED=1

# Minimal runtime + GStreamer (add bad/ugly/libav only if you really need them)
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.10 python3-pip python3-numpy \
    libgl1-mesa-glx libglib2.0-0 libusb-1.0-0 libgtk2.0-0 \
    libavcodec58 libavformat58 libswscale5 libtbbmalloc2 libtbb12 libdc1394-25 libv4l-0 \
    libgstreamer1.0-0 libgstreamer-plugins-base1.0-0 \
    gstreamer1.0-plugins-base gstreamer1.0-plugins-good \
 && rm -rf /var/lib/apt/lists/*

# Bring OpenCV from the builder
COPY --from=builder /usr/local/ /usr/local/
COPY --from=builder /usr/lib/python3/dist-packages/cv2* /usr/lib/python3/dist-packages/
RUN echo "/usr/local/lib" > /etc/ld.so.conf.d/opencv.conf && ldconfig

WORKDIR /app

# Requirements: install build deps temporarily, then purge
COPY --chown=0:0 requirements_gst.txt /app/
RUN apt-get update && apt-get install -y --no-install-recommends \
      gcc pkg-config libcairo2-dev libgirepository1.0-dev gir1.2-glib-2.0 python3-dev \
 && python3.10 -m pip install --upgrade pip \
 && pip install --no-cache-dir -r requirements_gst.txt \
 && pip uninstall -y opencv-python opencv-python-headless opencv-contrib-python || true \
 && apt-get purge -y gcc python3-dev libcairo2-dev libgirepository1.0-dev gir1.2-glib-2.0 \
 && apt-get autoremove -y && apt-get clean && rm -rf /var/lib/apt/lists/*

# Optional: strip Python extension .so files & clean tests/caches
RUN find /usr/local/lib/python3.10/dist-packages -type f -name "*.so" -exec strip --strip-unneeded {} + 2>/dev/null || true \
 && find /usr/local/lib/python3.10/dist-packages -type d \( -name tests -o -name test -o -name __pycache__ \) -prune -exec rm -rf {} + \
 && find /usr/local/lib/python3.10/dist-packages -type f -name "*.pyc" -delete

# App code
COPY --chown=0:0 src/ /app/src/
COPY --chown=0:0 main.py /app/

# Non-root user
RUN groupadd -r appuser && useradd -r -g appuser appuser && chown -R appuser:appuser /app
USER appuser

ENV PYTHONPATH="/app:${PYTHONPATH:-}"
EXPOSE 9990
CMD ["python3.10", "/app/main.py"]
