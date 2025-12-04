from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route("/voice_data", methods=["POST"])
def receive_voice_data():
    data = request.json
    print("Received:", data)

    # Example: control Raspberry Pi GPIO here

    return jsonify({"status": "ok", "message": "Data received"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5050)
