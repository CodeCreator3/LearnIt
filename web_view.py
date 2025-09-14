
from flask import Flask, render_template, request, redirect, url_for
from markupsafe import Markup
from chat import ask_question  # Import your function
import markdown
from class_creator import create_class as create_class_util

app = Flask(__name__)

# In-memory storage for classes
classes = {}


# Homepage
@app.route("/")
def home():
    return render_template("home.html", classes=classes)


# Create class route
@app.route("/create_class", methods=["GET", "POST"])
def create_class():
    import os
    import json as pyjson
    if request.method == "POST":
        class_name = request.form["class_name"].strip()
        if class_name:
            classes_dir = "classes"
            os.makedirs(classes_dir, exist_ok=True)
            json_path = os.path.join(classes_dir, f"{class_name}.json")
            if os.path.exists(json_path):
                with open(json_path, "r", encoding="utf-8") as f:
                    class_obj = pyjson.load(f)
            else:
                class_obj = create_class_util(class_name)
                # Recursively convert class objects to dicts/lists
                def serialize(obj):
                    if isinstance(obj, list):
                        return [serialize(i) for i in obj]
                    elif isinstance(obj, dict):
                        return {k: serialize(v) for k, v in obj.items()}
                    elif hasattr(obj, "__dict__"):
                        return {k: serialize(v) for k, v in obj.__dict__.items()}
                    else:
                        return obj
                with open(json_path, "w", encoding="utf-8") as f:
                    pyjson.dump(serialize(class_obj), f, ensure_ascii=False, indent=2)
            classes[class_name] = class_obj
            return redirect(url_for("view_class", class_name=class_name))
    return render_template("create_class.html")



# View class with units/lessons sidebar
@app.route("/class/<class_name>")
def view_class(class_name):
    import os
    import json as pyjson
    classes_dir = "classes"
    json_path = os.path.join(classes_dir, f"{class_name}.json")
    if not os.path.exists(json_path):
        return redirect(url_for("home"))
    with open(json_path, "r", encoding="utf-8") as f:
        class_data = pyjson.load(f)
    units = class_data["units"] if isinstance(class_data, dict) and "units" in class_data else []
    return render_template("class_view.html", class_name=class_name, units=units, selected_lesson=None, lesson_content=None)


# View lesson content
@app.route("/class/<class_name>/<unit_name>/<lesson_name>")
def view_lesson(class_name, unit_name, lesson_name):
    import os
    import json as pyjson
    classes_dir = "classes"
    json_path = os.path.join(classes_dir, f"{class_name}.json")
    if not os.path.exists(json_path):
        return redirect(url_for("home"))
    with open(json_path, "r", encoding="utf-8") as f:
        class_data = pyjson.load(f)
    units = class_data["units"] if isinstance(class_data, dict) and "units" in class_data else []
    selected_lesson = None
    lesson_content = None
    # Find the lesson object/content
    for unit in units:
        if unit.get("unit_name", "") == unit_name:
            lessons = unit.get("lessons", [])
            for lesson in lessons:
                lesson_name_val = lesson.get("lesson_name", "")
                if lesson_name_val == lesson_name:
                    selected_lesson = lesson_name_val
                    content_val = lesson.get("content", "")
                    # Render markdown
                    lesson_content = Markup(markdown.markdown(content_val or ""))
    return render_template("class_view.html", class_name=class_name, units=units, selected_lesson=selected_lesson, lesson_content=lesson_content)

if __name__ == "__main__":
    app.run(debug=True)
