from http.server import BaseHTTPRequestHandler, HTTPServer
import urllib.parse
import http.cookies
import hashlib
import db

SESSIONS = {}  

def hash_password(pw):
    return hashlib.sha256(pw.encode()).hexdigest()

class TaskServer(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/":
            return self.redirect("/login")
        elif self.path == "/register":
            return self.render("register.html")
        elif self.path == "/login":
            return self.render("login.html")
        elif self.path == "/dashboard":
            return self.serve_dashboard()
        elif self.path.startswith("/static/"):
            return self.serve_static(self.path[1:])
        else:
            self.send_error(404, "Page not found")

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        data = self.rfile.read(length).decode()
        form = urllib.parse.parse_qs(data)

        if self.path == "/register":
            return self.handle_register(form)
        elif self.path == "/login":
            return self.handle_login(form)
        elif self.path == "/task/create":
            return self.handle_task_create(form)
        elif self.path == "/task/update":
            return self.handle_task_update(form)
        elif self.path == "/task/delete":
            return self.handle_task_delete(form)
        else:
            self.send_error(404, "Page not found")

    
    def serve_dashboard(self):
        user_id = self.get_logged_in_user()
        if not user_id:
            return self.redirect("/login")

        # Filtering and sorting
        parsed = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed.query)
        status_filter = query.get("status", [None])[0]
        sort = query.get("sort", ["created_at"])[0]

        conn = db.get_connection()
        cur = conn.cursor(dictionary=True)

        sql = "SELECT * FROM tasks WHERE user_id=%s"
        params = [user_id]
        if status_filter:
            sql += " AND status=%s"
            params.append(status_filter)
        if sort in ["due_date", "status", "created_at"]:
            sql += f" ORDER BY {sort}"

        cur.execute(sql, params)
        tasks = cur.fetchall()
        cur.close()
        conn.close()

        html = "<h1>Task Dashboard</h1>"
        html += '<a href="/logout">Logout</a><br><br>'
        html += " <form method="POST" action="/task/create">
            <input name="title" placeholder="Task Title" required><br>
            <textarea name="description" placeholder="Description"></textarea><br>
            <label>Status:
              <select name="status">
                <option>Pending</option>
                <option>In Progress</option>
                <option>Completed</option>
              </select>
            </label><br>
            <label>Due Date: <input type="date" name="due_date"></label><br>
            <button type="submit">Add Task</button>
        </form><hr>"

        html += "<h2>Your Tasks</h2>"
        html += "<form method='GET' action='/dashboard'>Filter by Status: " \
                "<select name='status'><option value=''>All</option>" \
                "<option>Pending</option><option>In Progress</option><option>Completed</option></select>" \
                " Sort by: <select name='sort'><option>created_at</option><option>due_date</option><option>status</option></select>" \
                "<button type='submit'>Apply</button></form><br>"

        for t in tasks:
            html += f"""
            <div style='border:1px solid #ccc; padding:10px; margin:10px;'>
              <b>{t['title']}</b> ({t['status']})<br>
              Due: {t['due_date']}<br>
              {t['description']}<br>
              <form method="POST" action="/task/update">
                <input type="hidden" name="id" value="{t['id']}">
                <input type="text" name="title" value="{t['title']}"><br>
                <textarea name="description">{t['description']}</textarea><br>
                <select name="status">
                  <option {'selected' if t['status']=='Pending' else ''}>Pending</option>
                  <option {'selected' if t['status']=='In Progress' else ''}>In Progress</option>
                  <option {'selected' if t['status']=='Completed' else ''}>Completed</option>
                </select><br>
                <input type="date" name="due_date" value="{t['due_date'] or ''}"><br>
                <button type="submit">Update</button>
              </form>
              <form method="POST" action="/task/delete">
                <input type="hidden" name="id" value="{t['id']}">
                <button type="submit">Delete</button>
              </form>
            </div>
            """

        self.respond(html)

    
    def handle_register(self, form):
        username = form.get("username", [""])[0]
        password = form.get("password", [""])[0]
        conn = db.get_connection()
        cur = conn.cursor()
        try:
            cur.execute("INSERT INTO users (username, password) VALUES (%s,%s)",
                        (username, hash_password(password)))
            conn.commit()
            self.redirect("/login")
        except:
            self.respond("Registration failed.")
        finally:
            cur.close()
            conn.close()

    def handle_login(self, form):
        username = form.get("username", [""])[0]
        password = form.get("password", [""])[0]
        conn = db.get_connection()
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM users WHERE username=%s", (username,))
        user = cur.fetchone()
        cur.close()
        conn.close()
        if user and user["password"] == hash_password(password):
            sid = hashlib.sha256((username+password).encode()).hexdigest()
            SESSIONS[sid] = user["id"]
            self.send_response(302)
            self.send_header("Set-Cookie", f"session={sid}")
            self.send_header("Location", "/dashboard")
            self.end_headers()
        else:
            self.respond("Invalid login")


    def handle_task_create(self, form):
        uid = self.get_logged_in_user()
        if not uid: return self.redirect("/login")
        title = form.get("title", [""])[0]
        description = form.get("description", [""])[0]
        status = form.get("status", ["Pending"])[0]
        due_date = form.get("due_date", ["NULL"])[0] or None

        conn = db.get_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO tasks (user_id, title, description, status, due_date) VALUES (%s,%s,%s,%s,%s)",
                    (uid, title, description, status, due_date))
        conn.commit()
        cur.close()
        conn.close()
        self.redirect("/dashboard")

    def handle_task_update(self, form):
        uid = self.get_logged_in_user()
        if not uid: return self.redirect("/login")
        task_id = form.get("id", [""])[0]
        title = form.get("title", [""])[0]
        description = form.get("description", [""])[0]
        status = form.get("status", ["Pending"])[0]
        due_date = form.get("due_date", ["NULL"])[0] or None

        conn = db.get_connection()
        cur = conn.cursor()
        cur.execute("UPDATE tasks SET title=%s, description=%s, status=%s, due_date=%s WHERE id=%s AND user_id=%s",
                    (title, description, status, due_date, task_id, uid))
        conn.commit()
        cur.close()
        conn.close()
        self.redirect("/dashboard")

    def handle_task_delete(self, form):
        uid = self.get_logged_in_user()
        if not uid: return self.redirect("/login")
        task_id = form.get("id", [""])[0]
        conn = db.get_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM tasks WHERE id=%s AND user_id=%s", (task_id, uid))
        conn.commit()
        cur.close()
        conn.close()
        self.redirect("/dashboard")
    
       
    def render(self, filename):
        try:
            with open("templates/"+filename, "r") as f:
                html = f.read()
            self.respond(html)
        except FileNotFoundError:
            self.send_error(404, "Template not found")

    def serve_static(self, path):
        try:
            with open(path, "rb") as f:
                content = f.read()
            self.send_response(200)
            if path.endswith(".css"): self.send_header("Content-Type", "text/css")
            self.end_headers()
            self.wfile.write(content)
        except FileNotFoundError:
            self.send_error(404, "Static file not found")

    def respond(self, html):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode())

    def redirect(self, url):
        self.send_response(302)
        self.send_header("Location", url)
        self.end_headers()

    def get_logged_in_user(self):
        cookie_header = self.headers.get("Cookie")
        if cookie_header:
            cookies = http.cookies.SimpleCookie(cookie_header)
            if "session" in cookies:
                return SESSIONS.get(cookies["session"].value)
        return None

if __name__ == "__main__":
    print("Server running at http://localhost:8080")
    HTTPServer(("localhost", 8080), TaskServer).serve_forever()
          
