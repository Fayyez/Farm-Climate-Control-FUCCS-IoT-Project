import pandas as pd
from sklearn.ensemble import RandomForestRegressor
import pickle

df = pd.read_csv("data/sensor_data.csv")

X = df[["temp", "humidity", "pressure"]]
y = df["next_temp"]

model = RandomForestRegressor()
model.fit(X, y)

pickle.dump(model, open("model/temp_model.pkl", "wb"))