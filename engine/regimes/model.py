import numpy as np
import json
from typing import List, Dict, Any

class RegimeMLModel:
    """Pure NumPy multinomial logistic regression (softmax classifier) for market regimes.
    
    Predicts market regimes: TRENDING, RANGING, VOLATILE, REVERSAL, LOW_LIQUIDITY.
    No heavy C++ binary dependencies like Scikit-Learn or XGBoost, fully robust and portable.
    """
    
    def __init__(self, num_features: int = 5, num_classes: int = 5):
        self.num_features = num_features
        self.num_classes = num_classes
        
        # Initialize weights and biases to small random values for symmetry breaking
        np.random.seed(42)  # For reproducibility
        self.W = np.random.randn(num_features, num_classes) * 0.01
        self.b = np.zeros(num_classes)
        
        # Consistent regime label indices mapping
        self.class_labels = ["TRENDING", "RANGING", "VOLATILE", "REVERSAL", "LOW_LIQUIDITY"]

    def softmax(self, z: np.ndarray) -> np.ndarray:
        """Stable softmax calculation."""
        # Shift inputs to avoid overflow
        max_val = np.max(z, axis=1, keepdims=True)
        exp_z = np.exp(z - max_val)
        return exp_z / np.sum(exp_z, axis=1, keepdims=True)

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """Calculate class probabilities for each sample in X."""
        X_arr = np.asarray(X)
        if len(X_arr.shape) == 1:
            X_arr = X_arr.reshape(1, -1)
        z = np.dot(X_arr, self.W) + self.b
        return self.softmax(z)

    def predict(self, X: np.ndarray) -> np.ndarray:
        """Predict the class index with highest probability for each sample in X."""
        probs = self.predict_proba(X)
        return np.argmax(probs, axis=1)

    def compute_loss(self, X: np.ndarray, y: np.ndarray) -> float:
        """Calculate cross-entropy loss with L2 regularization."""
        X_arr = np.asarray(X)
        y_arr = np.asarray(y)
        probs = self.predict_proba(X_arr)
        n = X_arr.shape[0]
        # Cross-entropy loss with eps to prevent log(0)
        core_loss = -np.log(probs[np.arange(n), y_arr] + 1e-15)
        return float(np.mean(core_loss))

    def fit(self, X: np.ndarray, y: np.ndarray, epochs: int = 200, lr: float = 0.05):
        """Train the classifier using batch gradient descent."""
        X_arr = np.asarray(X)
        y_arr = np.asarray(y)
        n = X_arr.shape[0]
        
        # One-hot encode labels
        Y = np.zeros((n, self.num_classes))
        Y[np.arange(n), y_arr] = 1

        for _ in range(epochs):
            probs = self.predict_proba(X_arr)
            # Softmax cross-entropy gradients
            dW = np.dot(X_arr.T, (probs - Y)) / n
            db = np.sum(probs - Y, axis=0) / n
            
            # Weight update
            self.W -= lr * dW
            self.b -= lr * db

    def save_weights(self, filepath: str):
        """Persist model weights and configuration to a JSON file."""
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
        """Load model weights and configuration from a JSON file."""
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.W = np.array(data["W"])
        self.b = np.array(data["b"])
        self.num_features = int(data["num_features"])
        self.num_classes = int(data["num_classes"])
        self.class_labels = list(data["class_labels"])
