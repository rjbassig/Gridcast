import numpy as np
from sklearn.base import BaseEstimator, RegressorMixin
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


class SeasonalAR(RegressorMixin, BaseEstimator):
    """Direct autoregression with seasonal lag terms and ridge-stabilized coefficients."""

    def __init__(self):
        self.model = make_pipeline(StandardScaler(), Ridge(alpha=100.0))

    def fit(self, x, y):
        self.columns = [c for c in x.columns if c.startswith("lag_") or c == "seasonal_anchor"]
        self.model.fit(x[self.columns], y)
        return self

    def predict(self, x):
        return self.model.predict(x[self.columns])


class GRURegressor(RegressorMixin, BaseEstimator):
    """Small CPU GRU over ten irregular historical lags plus calendar/rolling context."""

    def __init__(self, epochs=5, hidden=24, seed=42):
        self.epochs, self.hidden, self.seed = epochs, hidden, seed

    def _network(self):
        import torch

        class Net(torch.nn.Module):
            def __init__(self, hidden, context):
                super().__init__()
                self.gru = torch.nn.GRU(1, hidden, batch_first=True)
                self.head = torch.nn.Linear(hidden + context, 1)

            def forward(self, x):
                _, h = self.gru(x[:, :10].flip(1).unsqueeze(-1))
                return self.head(torch.cat([h[-1], x[:, 10:]], dim=1)).flatten()

        return Net(self.hidden, self.nfeatures - 10)

    def fit(self, x, y):
        import torch

        torch.manual_seed(self.seed)
        torch.set_num_threads(2)
        self.nfeatures = x.shape[1]
        self.scaler = StandardScaler().fit(x)
        self.mean, self.std = float(np.mean(y)), float(np.std(y)) or 1
        self.net = self._network()
        self.net.train()
        tx = torch.tensor(self.scaler.transform(x), dtype=torch.float32)
        ty = torch.tensor((np.asarray(y) - self.mean) / self.std, dtype=torch.float32)
        opt = torch.optim.Adam(self.net.parameters(), lr=0.003)
        generator = torch.Generator().manual_seed(self.seed)
        for _ in range(self.epochs):
            for indices in torch.randperm(len(tx), generator=generator).split(256):
                opt.zero_grad()
                loss = torch.nn.functional.mse_loss(self.net(tx[indices]), ty[indices])
                loss.backward()
                torch.nn.utils.clip_grad_norm_(self.net.parameters(), 1)
                opt.step()
        self.net.eval()
        return self

    def predict(self, x):
        import torch

        with torch.no_grad():
            t = torch.tensor(self.scaler.transform(x), dtype=torch.float32)
            return self.net(t).numpy() * self.std + self.mean

    def __getstate__(self):
        state = self.__dict__.copy()
        net = state.pop("net", None)
        if net is not None:
            state["weights"] = net.state_dict()
        return state

    def __setstate__(self, state):
        weights = state.pop("weights", None)
        self.__dict__.update(state)
        if weights is not None:
            self.net = self._network()
            self.net.load_state_dict(weights)
            self.net.eval()


def build(name: str, cfg: dict, alpha: float = 100):
    if name == "ridge":
        return make_pipeline(StandardScaler(), Ridge(alpha=alpha))
    if name == "seasonal_ar":
        return SeasonalAR()
    if name == "xgboost":
        from xgboost import XGBRegressor

        return XGBRegressor(
            n_estimators=140,
            max_depth=4,
            learning_rate=0.05,
            n_jobs=2,
            random_state=cfg["seed"],
            objective="reg:squarederror",
        )
    if name == "lightgbm":
        from lightgbm import LGBMRegressor

        return LGBMRegressor(
            n_estimators=140,
            max_depth=5,
            num_leaves=24,
            learning_rate=0.05,
            n_jobs=2,
            random_state=cfg["seed"],
            verbosity=-1,
        )
    if name == "gru":
        return GRURegressor(cfg["gru_epochs"], cfg["gru_hidden"], cfg["seed"])
    raise ValueError(name)
