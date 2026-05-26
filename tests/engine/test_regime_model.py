import numpy as np
import pytest
import os
from engine.regimes.model import RegimeMLModel

def test_regime_model_forward():
    """Verify that predictions from initialized model have correct shape and valid probabilities."""
    # 5 features, 5 classes
    model = RegimeMLModel(num_features=5, num_classes=5)
    X = np.random.randn(10, 5)
    probs = model.predict_proba(X)
    assert probs.shape == (10, 5)
    assert np.allclose(np.sum(probs, axis=1), 1.0)
    
    preds = model.predict(X)
    assert preds.shape == (10,)
    assert np.all((preds >= 0) & (preds < 5))

def test_regime_model_training():
    """Verify that training the model decreases the cross-entropy loss on linearly separable data."""
    np.random.seed(42)
    model = RegimeMLModel(num_features=3, num_classes=2)
    
    # 100 samples, 3 features
    X = np.random.randn(100, 3)
    # Simple rule: if first feature > 0.0, class is 1, else 0
    y = (X[:, 0] > 0).astype(int)
    
    initial_loss = model.compute_loss(X, y)
    
    # Train the model
    model.fit(X, y, epochs=100, lr=0.1)
    
    final_loss = model.compute_loss(X, y)
    
    # Loss should decrease significantly
    assert final_loss < initial_loss
    assert final_loss < 0.3  # It should converge well on linearly separable data

def test_regime_model_save_and_load(tmp_path):
    """Verify model weights can be saved to disk and reloaded identically."""
    model = RegimeMLModel(num_features=4, num_classes=3)
    # Randomize weights
    model.W = np.random.randn(4, 3)
    model.b = np.random.randn(3)
    
    filepath = str(tmp_path / "test_weights.json")
    model.save_weights(filepath)
    
    assert os.path.exists(filepath)
    
    new_model = RegimeMLModel(num_features=4, num_classes=3)
    new_model.load_weights(filepath)
    
    assert np.allclose(model.W, new_model.W)
    assert np.allclose(model.b, new_model.b)
    assert model.class_labels == new_model.class_labels
