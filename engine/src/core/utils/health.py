import cv2
import numpy as np

class FrameHealthValidator:
    """
    A utility class to validate the visual quality of camera frames.
    Detects common issues like:
    1. Glitches/Artifacts (Green/Grey screens via Entropy)
    2. Connection drops (White/Black screens)
    3. Focus issues (Blur)
    """

    def __init__(self, entropy_thresh=4.0, white_thresh=0.6, blur_thresh=100.0, black_thresh=10.0):
        """
        :param entropy_thresh: Min entropy. Lower values indicate flat colors (grey/green screens).
        :param white_thresh: Max ratio of white pixels. Higher values indicate overexposure/signal loss.
        :param blur_thresh: Min Laplacian variance. Lower values indicate blur.
        :param black_thresh: Max mean intensity. Lower values indicate black screen/night mode issues.
        """
        self.entropy_thresh = entropy_thresh
        self.white_thresh = white_thresh
        self.blur_thresh = blur_thresh
        self.black_thresh = black_thresh

    def validate(self, frame):
        """
        Runs all health checks on a single frame.
        :param frame: BGR numpy array (Opencv image)
        :return: (is_healthy: bool, reasons: list[str])
        """
        if frame is None or frame.size == 0:
            return False, ["Empty Frame"]

        reasons = []
        
        # Convert to grayscale once for all checks
        if len(frame.shape) == 3:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        else:
            gray = frame

        # 1. Check for Glitch (Entropy & White Screen)
        is_glitched, glitch_reasons = self._check_glitch(gray)
        if is_glitched:
            reasons.extend(glitch_reasons)

        # 2. Check for Black Screen
        is_black, black_val = self._check_black_screen(gray)
        if is_black:
            reasons.append(f"Black Screen (Intensity: {black_val:.1f})")

        # 3. Check for Blur
        # (Optional: You might want to disable this for night vision cameras as they are naturally grainy)
        is_blurry, blur_val = self._check_blur(gray)
        if is_blurry:
            reasons.append(f"Blurry (Var: {blur_val:.1f})")

        is_healthy = len(reasons) == 0
        return is_healthy, reasons

    def _calculate_entropy(self, gray_frame):
        """Calculates Shannon entropy."""
        hist = cv2.calcHist([gray_frame], [0], None, [256], [0, 256]).ravel()
        p = hist.astype(np.float64)
        s = p.sum()
        if s <= 0: return 0.0
        p /= s
        p = p[p > 0]
        return float(-(p * np.log2(p)).sum())

    def _check_glitch(self, gray_frame):
        """
        Detects RTSP artifacts (smearing/grey blocks) using entropy 
        and connection loss (pure white screen).
        """
        reasons = []
        is_glitched = False

        # Entropy Check
        entropy_val = self._calculate_entropy(gray_frame)
        if entropy_val < self.entropy_thresh:
            reasons.append(f"Low Entropy/Glitch (Ent: {entropy_val:.2f})")
            is_glitched = True

        # White Screen Check
        white_ratio = float(np.sum(gray_frame > 220)) / float(gray_frame.size)
        if white_ratio > self.white_thresh:
            reasons.append(f"White Screen (Ratio: {white_ratio:.2f})")
            is_glitched = True

        return is_glitched, reasons

    def _check_blur(self, gray_frame):
        """
        Variance of Laplacian method.
        """
        laplacian_var = cv2.Laplacian(gray_frame, cv2.CV_64F).var()
        is_blurry = laplacian_var < self.blur_thresh
        return is_blurry, laplacian_var

    def _check_black_screen(self, gray_frame):
        """
        Simple mean intensity check.
        """
        mean_intensity = np.mean(gray_frame)
        is_black = mean_intensity < self.black_thresh
        return is_black, mean_intensity