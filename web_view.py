from flask import Flask, render_template, request
from markupsafe import Markup
from chat import ask_question  # Import your function
import markdown

app = Flask(__name__)

# Homepage
@app.route("/")
def home():
    return render_template("home.html")

# Ask route
@app.route("/ask", methods=["GET", "POST"])
def ask():
    if request.method == "POST":
        question = request.form["question"]
        answer = Markup(markdown.markdown(ask_question(input=question)))
        return render_template("answer.html", answer=answer)
    return render_template("ask.html")

if __name__ == "__main__":
    app.run(debug=True)
