"""Self-Supervised / Unsupervised ML Engine.

Autoencoder for anomaly detection — learn normal microstructure, flag deviations.
Isolation Forest for outlier detection — flag toxic conditions.
PCA for dimensionality reduction — reduce 147 gates to latent factors.
Online clustering — adapt regime definitions as new data arrives.
Reinforcement learning scaffolding — DQN/PPO for exit timing.
"""
from __future__ import annotations

import logging
import math
import os
from collections import deque
from typing import Any

import numpy as np

LOGGER = logging.getLogger("overseer.self_supervised")

AUTOENCODER_DIM = int(os.getenv("AUTOENCODER_DIM", "19"))
ANOMALY_THRESHOLD = float(os.getenv("ANOMALY_THRESHOLD", "3.0"))
IFORREST_CONTAMINATION = float(os.getenv("IFOREST_CONTAMINATION", "0.05"))
PCA_COMPONENTS = int(os.getenv("PCA_COMPONENTS", "5"))
ONLINE_CLUSTER_K = int(os.getenv("ONLINE_CLUSTER_K", "5"))
RL_STATE_DIM = int(os.getenv("RL_STATE_DIM", "19"))


class SimpleAutoencoder:
    """Lightweight autoencoder for anomaly detection on framework scores.

    Encoder: input -> hidden -> latent
    Decoder: latent -> hidden -> output
    Reconstruction error = anomaly score.
    """

    def __init__(self, input_dim: int = AUTOENCODER_DIM, latent_dim: int = 5, lr: float = 0.01) -> None:
        self.input_dim = input_dim
        self.latent_dim = latent_dim
        self.lr = lr
        scale = 0.1
        self.W_enc = np.random.randn(input_dim, latent_dim) * scale
        self.b_enc = np.zeros(latent_dim)
        self.W_dec = np.random.randn(latent_dim, input_dim) * scale
        self.b_dec = np.zeros(input_dim)
        self._trained = False
        self._error_history: deque[float] = deque(maxlen=1000)
        self._mean_error: float = 0.0
        self._std_error: float = 1.0

    def _sigmoid(self, x: np.ndarray) -> np.ndarray:
        return 1.0 / (1.0 + np.exp(-np.clip(x, -500, 500)))

    def encode(self, x: np.ndarray) -> np.ndarray:
        return self._sigmoid(x @ self.W_enc + self.b_enc)

    def decode(self, z: np.ndarray) -> np.ndarray:
        return self._sigmoid(z @ self.W_dec + self.b_dec)

    def reconstruct(self, x: np.ndarray) -> np.ndarray:
        return self.decode(self.encode(x))

    def train_step(self, x: np.ndarray) -> float:
        z = self.encode(x)
        x_hat = self.decode(z)
        error = x_hat - x
        recon_loss = float(np.mean(error ** 2))
        dec_delta = error * x_hat * (1 - x_hat)
        self.W_dec -= self.lr * z.reshape(-1, 1) @ dec_delta.reshape(1, -1)
        self.b_dec -= self.lr * dec_delta
        z_delta = (dec_delta @ self.W_dec.T) * z * (1 - z)
        self.W_enc -= self.lr * x.reshape(-1, 1) @ z_delta.reshape(1, -1)
        self.b_enc -= self.lr * z_delta
        self._error_history.append(recon_loss)
        if len(self._error_history) >= 50:
            err_arr = np.array(list(self._error_history))
            self._mean_error = float(np.mean(err_arr))
            self._std_error = float(np.std(err_arr))
            self._trained = True
        return recon_loss

    def anomaly_score(self, x: np.ndarray) -> float:
        x_hat = self.reconstruct(x)
        error = float(np.mean((x_hat - x) ** 2))
        if self._std_error > 1e-10:
            z_score = (error - self._mean_error) / self._std_error
        else:
            z_score = 0.0
        return z_score

    def is_anomaly(self, x: np.ndarray, threshold: float = ANOMALY_THRESHOLD) -> bool:
        return self.anomaly_score(x) > threshold


class SimpleIsolationForest:
    """Lightweight Isolation Forest for outlier detection.

    No sklearn dependency. Uses random partitioning.
    Shorter average path length = more anomalous.
    """

    def __init__(self, n_trees: int = 50, max_depth: int = 10) -> None:
        self.n_trees = n_trees
        self.max_depth = max_depth
        self._trees: list[dict[str, Any]] = []
        self._trained = False
        self._threshold: float = 0.6

    def fit(self, data: np.ndarray) -> None:
        if len(data) < 50:
            return
        n, d = data.shape
        self._trees = []
        subsample_size = min(256, n)
        for _ in range(self.n_trees):
            indices = np.random.choice(n, subsample_size, replace=False)
            subset = data[indices]
            tree = self._build_tree(subset, depth=0)
            self._trees.append(tree)
        scores = np.array([self._path_length(x, tree, 0) for x in data[:min(200, n)] for tree in self._trees[:10]])
        scores = scores.reshape(-1)
        if len(scores) > 10:
            self._threshold = float(np.percentile(scores, 85))
        self._trained = True

    def _build_tree(self, data: np.ndarray, depth: int) -> dict[str, Any]:
        if depth >= self.max_depth or len(data) <= 1:
            return {"is_leaf": True, "size": len(data)}
        d = data.shape[1]
        feature = np.random.randint(d)
        min_val = float(data[:, feature].min())
        max_val = float(data[:, feature].max())
        if min_val == max_val:
            return {"is_leaf": True, "size": len(data)}
        split = np.random.uniform(min_val, max_val)
        left_mask = data[:, feature] < split
        right_mask = ~left_mask
        if left_mask.sum() == 0 or right_mask.sum() == 0:
            return {"is_leaf": True, "size": len(data)}
        return {
            "is_leaf": False,
            "feature": feature,
            "split": split,
            "left": self._build_tree(data[left_mask], depth + 1),
            "right": self._build_tree(data[right_mask], depth + 1),
        }

    def _path_length(self, x: np.ndarray, tree: dict[str, Any], depth: int) -> float:
        if tree.get("is_leaf", False):
            return depth + self._c(tree.get("size", 1))
        if x[tree["feature"]] < tree["split"]:
            return self._path_length(x, tree["left"], depth + 1)
        else:
            return self._path_length(x, tree["right"], depth + 1)

    def _c(self, n: int) -> float:
        if n <= 1:
            return 0.0
        return 2.0 * (math.log(n - 1) + 0.5772156649) - 2.0 * (n - 1) / n

    def score(self, x: np.ndarray) -> float:
        if not self._trained or not self._trees:
            return 0.0
        avg_path = float(np.mean([self._path_length(x, tree, 0) for tree in self._trees]))
        n = 256
        c_n = self._c(n)
        if c_n <= 0:
            return 0.0
        return 2.0 ** (-avg_path / c_n)

    def is_outlier(self, x: np.ndarray) -> bool:
        return self.score(x) > self._threshold


class SimplePCA:
    """PCA via eigendecomposition of covariance matrix. No sklearn needed."""

    def __init__(self, n_components: int = PCA_COMPONENTS) -> None:
        self.n_components = n_components
        self.components: np.ndarray | None = None
        self.mean: np.ndarray | None = None
        self.explained_variance_ratio: list[float] = []
        self._trained = False

    def fit(self, data: np.ndarray) -> None:
        if len(data) < self.n_components + 1:
            return
        self.mean = np.mean(data, axis=0)
        centered = data - self.mean
        cov = np.cov(centered.T)
        if cov.ndim == 0:
            return
        eigenvalues, eigenvectors = np.linalg.eigh(cov)
        idx = np.argsort(eigenvalues)[::-1]
        eigenvalues = eigenvalues[idx]
        eigenvectors = eigenvectors[:, idx]
        total_var = float(eigenvalues.sum())
        if total_var > 0:
            self.explained_variance_ratio = [float(eigenvalues[i]) / total_var for i in range(min(self.n_components, len(eigenvalues)))]
        else:
            self.explained_variance_ratio = []
        self.components = eigenvectors[:, :self.n_components].T
        self._trained = True

    def transform(self, data: np.ndarray) -> np.ndarray:
        if not self._trained or self.mean is None or self.components is None:
            return np.zeros((len(data), self.n_components))
        centered = data - self.mean
        return centered @ self.components.T

    def inverse_transform(self, latent: np.ndarray) -> np.ndarray:
        if not self._trained or self.mean is None or self.components is None:
            return np.zeros(latent.shape[0])
        return latent @ self.components + self.mean


class OnlineKMeans:
    """Online k-means clustering that adapts as new data arrives."""

    def __init__(self, k: int = ONLINE_CLUSTER_K, lr: float = 0.1) -> None:
        self.k = k
        self.lr = lr
        self.centroids: np.ndarray | None = None
        self._counts: np.ndarray | None = None
        self._initialized = False

    def partial_fit(self, x: np.ndarray) -> int:
        if not self._initialized:
            self.centroids = x.reshape(1, -1).copy()
            self._counts = np.array([1.0])
            self._initialized = True
            return 0
        if len(self.centroids) < self.k:
            dists = np.linalg.norm(self.centroids - x, axis=1)
            if np.min(dists) > 0.5:
                self.centroids = np.vstack([self.centroids, x.reshape(1, -1)])
                self._counts = np.append(self._counts, 1.0)
                return len(self.centroids) - 1
        dists = np.linalg.norm(self.centroids - x, axis=1)
        nearest = int(np.argmin(dists))
        self.centroids[nearest] += self.lr * (x - self.centroids[nearest])
        self._counts[nearest] += 1
        return nearest

    def predict(self, x: np.ndarray) -> int:
        if not self._initialized or self.centroids is None:
            return 0
        dists = np.linalg.norm(self.centroids - x, axis=1)
        return int(np.argmin(dists))

    def get_cluster_sizes(self) -> list[int]:
        if self._counts is None:
            return []
        return [int(c) for c in self._counts]


class RLScaffold:
    """Reinforcement Learning scaffold for exit timing optimization.

    State: framework scores + position P&L + market microstructure
    Action: hold / exit / partial_close
    Reward: realized P&L adjusted for time and risk

    This is a scaffold — needs real trade data to train.
    """

    def __init__(self, state_dim: int = RL_STATE_DIM, n_actions: int = 3) -> None:
        self.state_dim = state_dim
        self.n_actions = n_actions
        self._q_table: dict[tuple, np.ndarray] = {}
        self._lr = 0.1
        self._gamma = 0.95
        self._epsilon = 0.1
        self._trained_steps: int = 0

    def _discretize_state(self, state: np.ndarray, bins: int = 5) -> tuple:
        discretized = []
        for val in state[:self.state_dim]:
            idx = min(bins - 1, max(0, int((val + 1) * bins / 2)))
            discretized.append(idx)
        return tuple(discretized)

    def select_action(self, state: np.ndarray) -> int:
        s = self._discretize_state(state)
        if s not in self._q_table:
            self._q_table[s] = np.zeros(self.n_actions)
        if np.random.random() < self._epsilon:
            return np.random.randint(self.n_actions)
        return int(np.argmax(self._q_table[s]))

    def update(self, state: np.ndarray, action: int, reward: float, next_state: np.ndarray, done: bool) -> None:
        s = self._discretize_state(state)
        s_next = self._discretize_state(next_state)
        if s not in self._q_table:
            self._q_table[s] = np.zeros(self.n_actions)
        if s_next not in self._q_table:
            self._q_table[s_next] = np.zeros(self.n_actions)
        target = reward if done else reward + self._gamma * np.max(self._q_table[s_next])
        self._q_table[s][action] += self._lr * (target - self._q_table[s][action])
        self._trained_steps += 1

    def get_policy(self, state: np.ndarray) -> dict[str, float]:
        s = self._discretize_state(state)
        if s not in self._q_table:
            return {"hold": 0.33, "exit": 0.33, "partial_close": 0.33}
        q = self._q_table[s]
        actions = ["hold", "exit", "partial_close"]
        return {actions[i]: round(float(q[i]), 4) for i in range(min(3, len(q)))}


class SelfSupervisedEngine:
    """Unified self-supervised / unsupervised ML engine."""

    def __init__(self) -> None:
        self.autoencoder = SimpleAutoencoder()
        self.iforest = SimpleIsolationForest()
        self.pca = SimplePCA()
        self.online_kmeans = OnlineKMeans()
        self.rl = RLScaffold()
        self._feature_buffer: deque[np.ndarray] = deque(maxlen=10000)
        self._tick_count: int = 0
        self._pca_trained: bool = False
        self._iforest_trained: bool = False

    def process_features(self, features: np.ndarray) -> dict[str, Any]:
        self._tick_count += 1
        self._feature_buffer.append(features)
        self.autoencoder.train_step(features)
        cluster = self.online_kmeans.partial_fit(features)
        anomaly_z = self.autoencoder.anomaly_score(features)
        is_anomaly = self.autoencoder.is_anomaly(features)
        outlier_score = self.iforest.score(features) if self._iforest_trained else 0.0
        is_outlier = self.iforest.is_outlier(features) if self._iforest_trained else False
        latent = self.pca.transform(features.reshape(1, -1)).flatten() if self._pca_trained else np.zeros(self.pca.n_components)
        if self._tick_count % 1000 == 0 and len(self._feature_buffer) >= 200:
            self._retrain_models()
        return {
            "anomaly_zscore": round(anomaly_z, 2),
            "is_anomaly": is_anomaly,
            "isolation_score": round(outlier_score, 4),
            "is_outlier": is_outlier,
            "online_cluster": cluster,
            "latent_factors": [round(float(v), 4) for v in latent],
            "autoencoder_error": round(self.autoencoder._mean_error, 6),
        }

    def _retrain_models(self) -> None:
        data = np.array(list(self._feature_buffer))
        if len(data) < 100:
            return
        self.pca.fit(data)
        self._pca_trained = True
        self.iforest.fit(data)
        self._iforest_trained = True
        LOGGER.info("Retrained PCA + Isolation Forest on %d samples", len(data))

    def get_rl_exit_decision(self, state: np.ndarray) -> dict[str, Any]:
        action = self.rl.select_action(state)
        policy = self.rl.get_policy(state)
        actions = ["hold", "exit", "partial_close"]
        return {
            "action": actions[action] if action < len(actions) else "hold",
            "policy": policy,
            "trained_steps": self.rl._trained_steps,
        }

    def get_status(self) -> dict[str, Any]:
        return {
            "tick_count": self._tick_count,
            "buffer_size": len(self._feature_buffer),
            "pca_trained": self._pca_trained,
            "iforest_trained": self._iforest_trained,
            "autoencoder_trained": self.autoencoder._trained,
            "online_clusters": self.online_kmeans.k,
            "rl_trained_steps": self.rl._trained_steps,
        }
