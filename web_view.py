from flask import Flask, render_template, request, redirect, url_for, jsonify
from markupsafe import Markup
from chat import ask_question  # Import your function
import markdown
from class_creator import create_class as create_class_util
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor

# Executor and job tracking
executor = ThreadPoolExecutor(max_workers=2)
jobs = {}
jobs_lock = threading.Lock()

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
    practice_problems = []
    prev_lesson = None
    next_lesson = None
    # Find the lesson object/content and prev/next
    for unit in units:
        if unit.get("unit_name", "") == unit_name:
            lessons = unit.get("lessons", [])
            for idx, lesson in enumerate(lessons):
                lesson_name_val = lesson.get("lesson_name", "")
                if lesson_name_val == lesson_name:
                    selected_lesson = lesson_name_val
                    content_val = lesson.get("content", "")
                    lesson_content = Markup(markdown.markdown(content_val or ""))
                    # Get practice problems
                    problems = lesson.get("practiceProblems", [])
                    for prob in problems:
                        question = Markup(markdown.markdown(prob.get("problem", "")))
                        solution = Markup(markdown.markdown(prob.get("solution", "")))
                        practice_problems.append({"problem": question, "solution": solution})
                    # Previous/next lesson
                    if idx > 0:
                        prev_lesson = lessons[idx-1].get("lesson_name", "")
                    if idx < len(lessons)-1:
                        next_lesson = lessons[idx+1].get("lesson_name", "")
    return render_template("class_view.html", class_name=class_name, units=units, selected_lesson=selected_lesson, lesson_content=lesson_content, practice_problems=practice_problems, unit_name=unit_name, prev_lesson=prev_lesson, next_lesson=next_lesson)

# Assistant Q&A for lesson
@app.route("/class/<class_name>/<unit_name>/<lesson_name>/ask", methods=["POST"])
def lesson_assistant(class_name, unit_name, lesson_name):
    import os
    import json as pyjson
    from chat import ask_question
    classes_dir = "classes"
    json_path = os.path.join(classes_dir, f"{class_name}.json")
    if not os.path.exists(json_path):
        return redirect(url_for("home"))
    with open(json_path, "r", encoding="utf-8") as f:
        class_data = pyjson.load(f)
    units = class_data["units"] if isinstance(class_data, dict) and "units" in class_data else []
    selected_lesson = None
    lesson_content = None
    practice_problems = []
    prev_lesson = None
    next_lesson = None
    assistant_answer = None
    question = request.form.get("assistant_question", "")
    # Find the lesson object/content and prev/next
    for unit in units:
        if unit.get("unit_name", "") == unit_name:
            lessons = unit.get("lessons", [])
            for idx, lesson in enumerate(lessons):
                lesson_name_val = lesson.get("lesson_name", "")
                if lesson_name_val == lesson_name:
                    selected_lesson = lesson_name_val
                    content_val = lesson.get("content", "")
                    lesson_content = Markup(markdown.markdown(content_val or ""))
                    problems = lesson.get("practiceProblems", [])
                    problems_text = "\n".join([
                        f"Q: {prob.get('problem', '')}\nA: {prob.get('solution', '')}" for prob in problems
                    ])
                    for prob in problems:
                        question_md = Markup(markdown.markdown(prob.get("problem", "")))
                        solution_md = Markup(markdown.markdown(prob.get("solution", "")))
                        practice_problems.append({"problem": question_md, "solution": solution_md})
                    if idx > 0:
                        prev_lesson = lessons[idx-1].get("lesson_name", "")
                    if idx < len(lessons)-1:
                        next_lesson = lessons[idx+1].get("lesson_name", "")
                    # Get assistant answer
                    if question:
                        # Provide lesson content and practice problems as context
                        prompt = f"You are an assistant helping a student with the following lesson.\nLesson content:\n{content_val}\n\nPractice Problems:\n{problems_text}\n\nStudent question: {question}"
                        assistant_answer = Markup(markdown.markdown(ask_question(prompt)))
    return render_template("class_view.html", class_name=class_name, units=units, selected_lesson=selected_lesson, lesson_content=lesson_content, practice_problems=practice_problems, unit_name=unit_name, prev_lesson=prev_lesson, next_lesson=next_lesson, assistant_answer=assistant_answer, assistant_question=question)



def _serialize(obj):
    # Recursively convert class objects to dicts/lists
    if isinstance(obj, list):
        return [_serialize(i) for i in obj]
    elif isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    elif hasattr(obj, "__dict__"):
        return {k: _serialize(v) for k, v in obj.__dict__.items()}
    else:
        return obj


def save_class_json(class_obj, filename=None):
    import os
    import json as pyjson
    classes_dir = "classes"
    os.makedirs(classes_dir, exist_ok=True)
    # determine filename
    class_name = None
    if isinstance(class_obj, dict):
        class_name = class_obj.get('class_name') or class_obj.get('title')
    elif hasattr(class_obj, 'class_name'):
        class_name = getattr(class_obj, 'class_name')
    if filename is None:
        safe_name = (class_name or 'class').replace(' ', '_')
        filename = f"{safe_name}.json"
    path = os.path.join(classes_dir, filename)
    with open(path, 'w', encoding='utf-8') as f:
        pyjson.dump(_serialize(class_obj), f, ensure_ascii=False, indent=2)
    return filename


def _run_create_job(class_name, job_id):
    try:
        with jobs_lock:
            jobs[job_id]['status'] = 'running'
        class_obj = create_class_util(class_name)
        filename = save_class_json(class_obj)
        with jobs_lock:
            jobs[job_id]['status'] = 'completed'
            jobs[job_id]['result'] = {'filename': filename, 'class_name': class_name, 'class': _serialize(class_obj)}
    except Exception as e:
        with jobs_lock:
            jobs[job_id]['status'] = 'failed'
            jobs[job_id]['error'] = str(e)


@app.route('/create_class_async', methods=['POST'])
def create_class_async():
    data = request.get_json() or {}
    class_name = data.get('class_name')
    if not class_name:
        return jsonify({'error': 'class_name is required'}), 400
    job_id = str(uuid.uuid4())
    with jobs_lock:
        jobs[job_id] = {'status': 'pending'}
    executor.submit(_run_create_job, class_name, job_id)
    return jsonify({'job_id': job_id}), 202


@app.route('/job_status/<job_id>', methods=['GET'])
def job_status(job_id):
    with jobs_lock:
        job = jobs.get(job_id)
        if job is None:
            return jsonify({'error': 'job not found'}), 404
        # Return a shallow copy
        response = dict(job)
    return jsonify(response)


if __name__ == "__main__":
    app.run(debug=True)
