from flask import Flask, render_template, request, jsonify
import pickle
import numpy as np

app = Flask(__name__)

# load models
temp_model = pickle.load(open("model/temp_model.pkl", "rb"))

@app.route("/")
def dashboard():
    return render_template("index.html")

@app.route("/predict_temp", methods=["POST"])
def predict_temp():
    data = request.json

    features = np.array([
        data["temp"],
        data["humidity"],
        data["pressure"]
    ]).reshape(1, -1)

    prediction = temp_model.predict(features)[0]

    return jsonify({"predicted_temp": prediction})

if __name__ == "__main__":
    app.run(debug=True)