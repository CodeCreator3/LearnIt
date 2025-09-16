from flask import Flask, render_template, request, redirect, url_for, jsonify, send_file
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
futures = {}

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
            # Attempt to redirect to the first unit and lesson (U1 L1) if available
            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    saved = __import__('json').load(f)
                units = saved.get('units') if isinstance(saved, dict) else None
                if units and len(units) > 0:
                    first_unit = units[0]
                    unit_name = first_unit.get('unit_name') or ''
                    lessons = first_unit.get('lessons') or []
                    if lessons and len(lessons) > 0:
                        lesson_name = lessons[0].get('lesson_name') or ''
                        return redirect(url_for('view_lesson', class_name=class_name, unit_name=unit_name, lesson_name=lesson_name))
            except Exception:
                pass
            # fallback: go to home
            return redirect(url_for('home'))
    return render_template("create_class.html")


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
        # progress callback will update job entry
        def progress_callback(progress):
            import time as _time
            try:
                # attach a timestamp so clients can continuously update remaining estimate
                pcopy = dict(progress) if isinstance(progress, dict) else {'percent': progress}
                pcopy['_ts'] = _time.time()
            except Exception:
                pcopy = progress
            with jobs_lock:
                jobs[job_id]['progress'] = pcopy

        class_obj = create_class_util(class_name, progress_callback=progress_callback)
        filename = save_class_json(class_obj)
        # determine first unit/lesson for quick linking
        serialized = _serialize(class_obj)
        first_unit = None
        first_lesson = None
        try:
            units = serialized.get('units') if isinstance(serialized, dict) else None
            if units and len(units) > 0:
                first = units[0]
                first_unit = first.get('unit_name') if isinstance(first, dict) else None
                lessons = first.get('lessons') if isinstance(first, dict) else []
                if lessons and len(lessons) > 0:
                    first_lesson = lessons[0].get('lesson_name') if isinstance(lessons[0], dict) else None
        except Exception:
            first_unit = None
            first_lesson = None
        with jobs_lock:
            jobs[job_id]['status'] = 'completed'
            jobs[job_id]['result'] = {'filename': filename, 'class_name': class_name, 'class': serialized, 'unit': first_unit, 'lesson': first_lesson, 'job_id': job_id}
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
        # include the requested class_name and job_id right away so UI can show the job immediately
        jobs[job_id] = {'status': 'pending', 'result': {'class_name': class_name, 'job_id': job_id}}
    future = executor.submit(_run_create_job, class_name, job_id)
    with jobs_lock:
        futures[job_id] = future
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


@app.route('/cancel_job/<job_id>', methods=['POST'])
def cancel_job(job_id):
    with jobs_lock:
        job = jobs.get(job_id)
        fut = futures.get(job_id)
        if job is None:
            return jsonify({'error': 'job not found'}), 404
        # try to cancel
        cancelled = False
        if fut:
            cancelled = fut.cancel()
        # remove job from tracking so polling clients no longer see it
        try:
            if job_id in jobs:
                del jobs[job_id]
        except Exception:
            pass
        try:
            if job_id in futures:
                del futures[job_id]
        except Exception:
            pass
    return jsonify({'cancelled': bool(cancelled)})


@app.route('/delete_class/<class_name>', methods=['DELETE'])
def delete_class(class_name):
    import os
    classes_dir = 'classes'
    path = os.path.join(classes_dir, f"{class_name}.json")
    if not os.path.exists(path):
        return jsonify({'error': 'class not found'}), 404
    try:
        os.remove(path)
        # remove in-memory entry if present
        if class_name in classes:
            del classes[class_name]
        return jsonify({'deleted': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/jobs_list', methods=['GET'])
def jobs_list():
    with jobs_lock:
        # produce a shallow copy of jobs with id included
        out = {jid: dict(info) for jid, info in jobs.items()}
    return jsonify(out)


@app.route('/classes_list', methods=['GET'])
def classes_list():
    import os
    import json as pyjson
    classes_dir = 'classes'
    if not os.path.exists(classes_dir):
        return jsonify([])
    out = []
    for f in os.listdir(classes_dir):
        if not f.endswith('.json'):
            continue
        path = os.path.join(classes_dir, f)
        name = os.path.splitext(f)[0]
        unit_name = None
        lesson_name = None
        try:
            with open(path, 'r', encoding='utf-8') as fh:
                data = pyjson.load(fh)
            units = data.get('units') if isinstance(data, dict) else None
            if units and len(units) > 0:
                first_unit = units[0]
                unit_name = first_unit.get('unit_name') or None
                lessons = first_unit.get('lessons') or []
                if lessons and len(lessons) > 0:
                    lesson_name = lessons[0].get('lesson_name') or None
        except Exception:
            # on any error, just return the filename with nulls
            pass
        out.append({'name': name, 'unit': unit_name, 'lesson': lesson_name})
    return jsonify(out)


if __name__ == "__main__":
    app.run(debug=True)


@app.route('/class_image/<class_name>')
def class_image(class_name):
    import os
    import io
    from PIL import Image

    safe_name = str(class_name).replace(' ', '_').replace('/', '_')
    images_dir = 'images'
    os.makedirs(images_dir, exist_ok=True)
    path = os.path.join(images_dir, f"{safe_name}.png")
    # Serve cached image if present
    if os.path.exists(path):
        return send_file(path, mimetype='image/png')

    # Try to generate using diffusers + torch (Stable Diffusion). If unavailable or any error, return transparent PNG.
    try:
        import torch
        from diffusers import StableDiffusionPipeline

        device = "cuda" if torch.cuda.is_available() else "cpu"
        model_id = "runwayml/stable-diffusion-v1-5"

        # load pipeline (may require significant resources and model files to be present locally)
        pipe = StableDiffusionPipeline.from_pretrained(model_id)
        pipe = pipe.to(device)

        prompt = f"Subtle abstract background representing the topic '{class_name}', soft pastel colors, minimal, no text, simple shapes, high quality, suitable as a faded background for an educational card"
        generator = None
        try:
            # deterministic seed based on class name
            seed = abs(hash(class_name)) % (2**32)
            if device == 'cuda':
                generator = torch.Generator(device).manual_seed(seed)
            else:
                generator = torch.Generator().manual_seed(seed)
        except Exception:
            generator = None

        result = pipe(prompt, guidance_scale=7.0, height=512, width=512, generator=generator)
        image = result.images[0]
        # Save to cache
        image.save(path)
        return send_file(path, mimetype='image/png')
    except Exception as e:
        # Fallback: transparent PNG
        buf = io.BytesIO()
        img = Image.new('RGBA', (512, 512), (255, 255, 255, 0))
        img.save(buf, format='PNG')
        buf.seek(0)
        return send_file(buf, mimetype='image/png')
