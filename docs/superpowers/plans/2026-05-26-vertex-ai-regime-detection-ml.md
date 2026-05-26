# Vertex AI / ML-based Regime Detection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Efloud-bot'a geçmiş verilerden öğrenen ve her gün otomatik olarak yeniden eğitilen (daily automated retraining pipeline), kural tabanlı ADX/ATR rejim algılayıcısını zenginleştiren, sıfır bağımlılıklı (pure NumPy/Pandas) bir makine öğrenimi (Logistic Regression / Softmax) rejim sınıflandırıcısı layer'ı eklemek.

**Architecture:** 
1. `engine/regimes/model.py` modülü pure NumPy softmax sınıflandırıcıyı ve gradient descent tabanlı eğitim mekanizmasını barındırır.
2. `engine/regimes/train.py` modülü günlük otomatik eğitim pipeline'ını koşturur: geçmiş OHLCV verilerinden özellikleri (ADX, BBW, ATR, Vol-Z) çıkartır, kural tabanlı etiketler üzerinden yarı-denetimli (semi-supervised) bir şekilde modeli eğitir ve ağırlıkları `state/regime_model_weights.json` dosyasına kaydeder.
3. `engine/regimes/__init__.py` içindeki `RegimeDetector` bu ağırlıkları kullanarak model çıkarımı yapar ve kural tabanlı rejimlerle birleştirerek (confluence ensembling) daha pürüzsüz ve gürültüden arındırılmış rejim kararları üretir.

**Tech Stack:** Python 3.10+, NumPy, Pandas, pytest.

---

### Task 1: NumPy ML Model Definition (Sınıflandırıcı & Eğitim)

**Files:**
- Create: `engine/regimes/model.py`
- Test: `tests/engine/test_regime_model.py`

- [ ] **Step 1: Write the failing test**
  `tests/engine/test_regime_model.py` dosyasını oluşturarak modelin ağırlık yükleme, ileri besleme (softmax) ve eğitim (fit) fonksiyonlarını test eden bir TDD test şablonu yazın.
  ```python
  import numpy as np
  import pytest
  from engine.regimes.model import RegimeMLModel

  def test_regime_model_forward():
      # 5 features, 4 classes (TRENDING, RANGING, VOLATILE, REVERSAL)
      model = RegimeMLModel(num_features=5, num_classes=4)
      X = np.random.randn(10, 5)
      probs = model.predict_proba(X)
      assert probs.shape == (10, 4)
      assert np.allclose(np.sum(probs, axis=1), 1.0)

  def test_regime_model_training():
      np.random.seed(42)
      model = RegimeMLModel(num_features=3, num_classes=2)
      # Simple linearly separable data
      X = np.random.randn(100, 3)
      # Target class is 1 if first feature > 0 else 0
      y = (X[:, 0] > 0).astype(int)
      
      # Initial loss
      initial_loss = model.compute_loss(X, y)
      
      # Train model
      model.fit(X, y, epochs=100, lr=0.1)
      
      final_loss = model.compute_loss(X, y)
      assert final_loss < initial_loss
  ```

- [ ] **Step 2: Run test to verify it fails**
  Run: `.venv\Scripts\pytest tests/engine/test_regime_model.py -v`
  Expected: FAIL (ModuleNotFoundError: No module named 'engine.regimes.model')

- [ ] **Step 3: Write minimal implementation**
  `engine/regimes/model.py` dosyasını oluşturun ve pure NumPy tabanlı softmax sınıflandırıcıyı yazın.
  ```python
  import numpy as np
  import json
  from typing import List, Dict, Any

  class RegimeMLModel:
      def __init__(self, num_features: int = 5, num_classes: int = 5):
          self.num_features = num_features
          self.num_classes = num_classes
          # Initialize weights and biases to small random values
          self.W = np.random.randn(num_features, num_classes) * 0.01
          self.b = np.zeros(num_classes)
          
          # Class map: maps integer indices to Regime labels
          self.class_labels = ["TRENDING", "RANGING", "VOLATILE", "REVERSAL", "LOW_LIQUIDITY"]

      def softmax(self, z: np.ndarray) -> np.ndarray:
          # Stability trick: subtract max
          exp_z = np.exp(z - np.max(z, axis=1, keepdims=True))
          return exp_z / np.sum(exp_z, axis=1, keepdims=True)

      def predict_proba(self, X: np.ndarray) -> np.ndarray:
          z = np.dot(X, self.W) + self.b
          return self.softmax(z)

      def predict(self, X: np.ndarray) -> np.ndarray:
          probs = self.predict_proba(X)
          return np.argmax(probs, axis=1)

      def compute_loss(self, X: np.ndarray, y: np.ndarray) -> float:
          probs = self.predict_proba(X)
          n = X.shape[0]
          # Cross-entropy loss
          core_loss = -np.log(probs[np.arange(n), y] + 1e-15)
          return float(np.mean(core_loss))

      def fit(self, X: np.ndarray, y: np.ndarray, epochs: int = 200, lr: float = 0.05):
          n = X.shape[0]
          # One-hot encode targets
          Y = np.zeros((n, self.num_classes))
          Y[np.arange(n), y] = 1

          for epoch in range(epochs):
              probs = self.predict_proba(X)
              # Gradients
              dW = np.dot(X.T, (probs - Y)) / n
              db = np.sum(probs - Y, axis=0) / n
              # Update weights
              self.W -= lr * dW
              self.b -= lr * db

      def save_weights(self, filepath: str):
          data = {
              "W": self.W.tolist(),
              "b": self.b.tolist(),
              "num_features": self.num_features,
              "num_classes": self.num_classes,
              "class_labels": self.class_labels
          }
          with open(filepath, "w", encoding="utf-8") as f:
              json.dump(data, f, indent=2)

      def load_weights(self, filepath: str):
          with open(filepath, "r", encoding="utf-8") as f:
              data = json.load(f)
          self.W = np.array(data["W"])
          self.b = np.array(data["b"])
          self.num_features = data["num_features"]
          self.num_classes = data["num_classes"]
          self.class_labels = data["class_labels"]
  ```

- [ ] **Step 4: Run test to verify it passes**
  Run: `.venv\Scripts\pytest tests/engine/test_regime_model.py -v`
  Expected: PASS

- [ ] **Step 5: Commit**
  ```bash
  git add engine/regimes/model.py tests/engine/test_regime_model.py
  git commit -m "feat(ml): implement pure NumPy softmax classifier for regime detection"
  ```

---

### Task 2: Automated Training Pipeline (Veri & Özellik Çıkarımı)

**Files:**
- Create: `engine/regimes/train.py`
- Test: `tests/engine/test_regime_train.py`

- [ ] **Step 1: Write the failing test**
  `tests/engine/test_regime_train.py` dosyasını oluşturarak geçmiş OHLCV verilerinden özelliklerin doğru çıkartıldığını, etiketlendiğini ve modelin eğitilip kaydedildiğini doğrulayın.
  ```python
  import pandas as pd
  import numpy as np
  import pytest
  from engine.regimes.train import build_features_and_labels, run_auto_train

  def test_build_features_and_labels():
      np.random.seed(42)
      df = pd.DataFrame({
          "open": np.random.rand(100) * 100,
          "high": np.random.rand(100) * 100,
          "low": np.random.rand(100) * 100,
          "close": np.random.rand(100) * 100,
          "volume": np.random.rand(100) * 1000,
      })
      X, y = build_features_and_labels(df)
      assert X.shape[0] == y.shape[0]
      assert X.shape[1] == 5  # 5 features
  ```

- [ ] **Step 2: Run test to verify it fails**
  Run: `.venv\Scripts\pytest tests/engine/test_regime_train.py -v`
  Expected: FAIL (ModuleNotFoundError: No module named 'engine.regimes.train')

- [ ] **Step 3: Write minimal implementation**
  `engine/regimes/train.py` modülünü oluşturun:
  ```python
  import numpy as np
  import pandas as pd
  import json
  from pathlib import Path
  from engine.regimes.model import RegimeMLModel
  from engine.regimes import RegimeDetector

  ROOT = Path(__file__).resolve().parents[2]

  def build_features_and_labels(df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
      """Past OHLCV'den model özelliklerini ve kural tabanlı etiketleri türet."""
      detector = RegimeDetector()
      
      # Prepare inputs
      X_list = []
      y_list = []
      
      # Class index mapping
      label_map = {"TRENDING": 0, "RANGING": 1, "VOLATILE": 2, "REVERSAL": 3, "LOW_LIQUIDITY": 4, "UNKNOWN": 1}

      # Sliding window calculation
      # Minimum length needed for indicators (adx_period * 2 = 28)
      start_idx = 40
      
      # Precalculate indicators for speed
      # Current ATR ratio
      h, l, c = df["high"].values, df["low"].values, df["close"].values
      tr = np.maximum(h[1:] - l[1:], np.maximum(abs(h[1:] - c[:-1]), abs(l[1:] - c[:-1])))
      
      for i in range(start_idx, len(df)):
          sub_df = df.iloc[:i+1]
          analysis = detector.analyze(sub_df)
          
          # Feature 1: ADX
          feat_adx = analysis.adx / 100.0  # Normalize to 0-1
          # Feature 2: BB Width Ratio
          feat_bbw = min(analysis.bb_width, 5.0) / 2.0  # Normalized
          # Feature 3: ATR Ratio
          feat_atr = min(analysis.atr_ratio, 5.0) / 2.0  # Normalized
          
          # Feature 4: Price Standard Deviation of returns
          ret = df["close"].iloc[i-20:i+1].pct_change().std()
          feat_ret_std = min(ret * 100.0, 5.0)  # Normalized
          
          # Feature 5: Volume Z-Score
          vol_sub = df["volume"].iloc[i-20:i+1]
          feat_vol = 0.0
          if vol_sub.std() > 0:
              feat_vol = float((df["volume"].iloc[i] - vol_sub.mean()) / vol_sub.std())
          feat_vol = max(min(feat_vol, 3.0), -3.0)  # Clamp
          
          X_list.append([feat_adx, feat_bbw, feat_atr, feat_ret_std, feat_vol])
          y_list.append(label_map.get(analysis.regime, 1))

      return np.array(X_list), np.array(y_list)

  def run_auto_train(df: pd.DataFrame, weights_filename: str = "regime_model_weights.json") -> dict:
      """Yarı denetimli olarak modeli geçmiş verilerden eğitip kaydeder."""
      X, y = build_features_and_labels(df)
      if len(X) < 10:
          return {"success": False, "reason": "Insufficient training samples"}
          
      model = RegimeMLModel(num_features=5, num_classes=5)
      initial_loss = model.compute_loss(X, y)
      
      model.fit(X, y, epochs=150, lr=0.1)
      final_loss = model.compute_loss(X, y)
      
      weights_path = ROOT / "state" / weights_filename
      weights_path.parent.mkdir(parents=True, exist_ok=True)
      model.save_weights(str(weights_path))
      
      return {
          "success": True,
          "samples": len(X),
          "initial_loss": initial_loss,
          "final_loss": final_loss,
          "weights_path": str(weights_path)
      }
  ```

- [ ] **Step 4: Run test to verify it passes**
  Run: `.venv\Scripts\pytest tests/engine/test_regime_train.py -v`
  Expected: PASS

- [ ] **Step 5: Commit**
  ```bash
  git add engine/regimes/train.py tests/engine/test_regime_train.py
  git commit -m "feat(ml): implement automated ML training pipeline with sliding features extraction"
  ```

---

### Task 3: RegimeDetector Integration (Confluence Ensemble)

**Files:**
- Modify: `engine/regimes/__init__.py`
- Test: `tests/engine/test_regime_detector_ml.py`

- [ ] **Step 1: Write the failing test**
  `tests/engine/test_regime_detector_ml.py` dosyasını oluşturarak RegimeDetector'ın ML model ağırlıklarını yüklediğini ve çıkarım sonuçlarını kural tabanlı analizle birleştirdiğini doğrulayın.
  ```python
  import pandas as pd
  import numpy as np
  import pytest
  from engine.regimes import RegimeDetector

  def test_regime_detector_ml_ensemble():
      # Create synthetic data
      np.random.seed(42)
      df = pd.DataFrame({
          "open": np.random.rand(100) * 100,
          "high": np.random.rand(100) * 100,
          "low": np.random.rand(100) * 100,
          "close": np.random.rand(100) * 100,
          "volume": np.random.rand(100) * 1000,
      })
      
      detector = RegimeDetector()
      # Analyze should work seamlessly and produce a regime analysis
      analysis = detector.analyze(df)
      assert analysis.regime in ["TRENDING", "RANGING", "VOLATILE", "REVERSAL", "LOW_LIQUIDITY", "UNKNOWN"]
  ```

- [ ] **Step 2: Run test to verify it fails**
  Run: `.venv\Scripts\pytest tests/engine/test_regime_detector_ml.py -v`
  Expected: PASS (çünkü henüz ML entegrasyonu yok ama detector çalışıyor. Biz modify edince ML tabanlı oylama da aktif olacak).

- [ ] **Step 3: Modify `engine/regimes/__init__.py`**
  `RegimeDetector` sınıfının init ve `analyze` fonksiyonlarına model çıkarımını (softmax probability voting) ekleyin. Eğer model eğitilmemişse veya ağırlık dosyası yoksa, kural tabanlı çıkarım pürüzsüzce devam eder (graceful degradation).
  ```python
  # engine/regimes/__init__.py'ye eklenecekler:
  from pathlib import Path
  import json
  from engine.regimes.model import RegimeMLModel

  # RegimeDetector.__init__ metoduna ekleyin:
  # ... mevcut init kodunun sonuna:
  self.weights_path = Path(__file__).resolve().parents[2] / "state" / "regime_model_weights.json"
  self.model = None
  self._load_ml_model()

  # RegimeDetector sınıfına yeni metod ekle:
  def _load_ml_model(self):
      if self.weights_path.exists():
          try:
              self.model = RegimeMLModel(num_features=5, num_classes=5)
              self.model.load_weights(str(self.weights_path))
          except Exception:
              self.model = None

  # RegimeDetector._analyze_raw metodunun sonuna ekleyin:
  # (Satır 129 civarı, default 'weak trend' kararının hemen öncesinde ML ensemble layer'ı):
  if self.model is not None:
      try:
          # Extract current feature vector
          feat_adx = adx_val / 100.0
          feat_bbw = min(bb_w_ratio, 5.0) / 2.0
          feat_atr = min(atr_ratio, 5.0) / 2.0
          
          ret = df["close"].iloc[-21:].pct_change().std()
          feat_ret_std = min(ret * 100.0, 5.0)
          
          vol_sub = df["volume"].iloc[-21:]
          feat_vol = 0.0
          if vol_sub.std() > 0:
              feat_vol = float((df["volume"].iloc[-1] - vol_sub.mean()) / vol_sub.std())
          feat_vol = max(min(feat_vol, 3.0), -3.0)
          
          X_vec = np.array([[feat_adx, feat_bbw, feat_atr, feat_ret_std, feat_vol]])
          probs = self.model.predict_proba(X_vec)[0]
          ml_idx = np.argmax(probs)
          ml_regime = self.model.class_labels[ml_idx]
          ml_confidence = int(probs[ml_idx] * 100)
          
          # Confluence Voting: Combine Rule-based score and ML probability
          # If ML model has high confidence (> 65%), and aligns with indicators, promote it
          notes.append(f"ML Model: {ml_regime} ({ml_confidence}%)")
          
          # Ensemble voting rule
          if ml_confidence >= 65:
              # Merge logic
              return RegimeAnalysis(ml_regime, int((ml_confidence + 80) / 2), adx_val, bb_w_ratio, atr_ratio, htf_aligned, notes)
      except Exception as e:
          notes.append(f"ML Inference skipped: {e}")
  ```

- [ ] **Step 4: Run test to verify it passes**
  Run: `.venv\Scripts\pytest tests/engine/test_regime_detector_ml.py -v`
  Expected: PASS

- [ ] **Step 5: Run full regime test diagnostic script**
  Run: `.venv\Scripts\python.exe test_regime.py`
  Expected: PASS/Classifications outputted correctly with ML notes!

- [ ] **Step 6: Commit**
  ```bash
  git add engine/regimes/__init__.py
  git commit -m "feat(regimes): integrate ML probability ensemble into core RegimeDetector"
  ```

---

### Task 4: Integration with SafeOrchestrator Cycle & Auto-Training Loop

**Files:**
- Modify: `engine/safe_orchestrator.py`
- Test: `tests/engine/test_orchestrator_regime_ml.py`

- [ ] **Step 1: Modify `engine/safe_orchestrator.py`**
  `SafeOrchestrator.run_cycle()` veya `run()` metoduna günlük otomatik eğitim tetikleyicisi ekleyin. Her 24 saatte bir, `engine/regimes/train.py:run_auto_train` asenkron bir thread/task olarak veya cycle içinde çalışır ve model ağırlıklarını günceller.
  ```python
  # safe_orchestrator.py'ye import ekle:
  from engine.regimes.train import run_auto_train

  # SafeOrchestrator init içine ekle:
  self.last_regime_training_time = None

  # run_cycle veya tick loop içerisine ekle:
  def check_and_train_regime_model(self, df_dict: dict):
      import datetime
      now = datetime.datetime.now(datetime.timezone.utc)
      if self.last_regime_training_time is None or (now - self.last_regime_training_time).total_seconds() > 86400:
          # Train model using BTC/USDT or core symbol historical df
          if "BTC/USDT" in df_dict:
              df_train = df_dict["BTC/USDT"]
              if len(df_train) >= 100:
                  try:
                      log.info("Starting Daily Automated Regime ML model retraining...")
                      res = run_auto_train(df_train)
                      if res["success"]:
                          log.info(f"Regime ML model retrained successfully! Samples: {res['samples']}, Loss: {res['final_loss']:.4f}")
                          self.last_regime_training_time = now
                          # Reload weights in detector
                          self.detector._load_ml_model()
                      else:
                          log.warning(f"Regime ML auto-train skipped: {res.get('reason')}")
                  except Exception as e:
                      log.error(f"Error during automated regime ML training: {e}")
  ```

- [ ] **Step 2: Write verification test**
  `tests/engine/test_orchestrator_regime_ml.py` dosyasını oluşturarak SafeOrchestrator'ın cycle içinde ML training fonksiyonunu çağırdığını doğrulayın.

- [ ] **Step 3: Run the unit test suite**
  Run: `.venv\Scripts\pytest tests/engine/test_orchestrator_regime_ml.py -v`
  Expected: PASS

- [ ] **Step 4: Commit**
  ```bash
  git add engine/safe_orchestrator.py tests/engine/test_orchestrator_regime_ml.py
  git commit -m "feat(orchestrator): integrate daily automated retraining pipeline into cycle execution"
  ```

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-26-vertex-ai-regime-detection-ml.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
