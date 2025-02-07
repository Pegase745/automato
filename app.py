from flask import Flask, render_template, g, redirect, jsonify, url_for, request, session
from flask_sqlalchemy import SQLAlchemy
import pika
import json
import os
import csv
from werkzeug import secure_filename
from flask_migrate import Migrate
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datatables import ColumnDT, DataTables
# from flask.ext.migrate import Migrate, MigrateCommand
# from whoosh.analysis import StemmingAnalyzer

import datetime

app = Flask(__name__)
app.config.from_pyfile('config.py')

db = SQLAlchemy(app)

from model import contacts, scrape_form, import_file, scrape_task, job_form, job_task, template, template_form, contact_search, contact_filter,\
    LoginForm, Users, SignupForm,  project_form, Project, driver_path_form , contact_selector , job_group_form , add_contact , job_test_form

migrate = Migrate(app, db)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

global visit
visit = 0


RABBITMQ_HOST = os.environ.get('AMPQ_HOST')


def connect_queue():
    if not hasattr(g, 'rabbitmq'):
        params = pika.URLParameters(RABBITMQ_HOST)
        params.socket_timeout = 5
        g.rabbitmq = pika.BlockingConnection(params)
    return g.rabbitmq


def get_scraper_queue():
    if not hasattr(g, 'task_queue'):
        conn = connect_queue()
        channel = conn.channel()
        channel.queue_declare(queue='scraper_queue', durable=True)
        channel.queue_bind(exchange='amq.direct', queue='scraper_queue')
        g.task_queue = channel
    return g.task_queue


def destroy_scraper_queue():
    if hasattr(g, 'task_queue'):
        g.task_queue.queue_delete(queue="scraper_queue")
    else:
        print("Scraper Queue not available")


def get_mssg_queue():
    if not hasattr(g, 'mssg_queue'):
        conn = connect_queue()
        channel = conn.channel()
        channel.queue_declare(queue='mssg_queue', durable=True)
        channel.queue_bind(exchange='amq.direct', queue='mssg_queue')
        g.mssg_queue = channel
    return g.mssg_queue


@app.teardown_appcontext
def close_queue(error):
    if hasattr(g, 'rabbitmq'):
        g.rabbitmq.close()


@app.route('/login', methods=['GET', 'POST'])
def login():
    """
    """
    form = LoginForm()
    session['mssg'] = ""
    if form.validate_on_submit():
        user = Users.query.filter_by(username=form.username.data).first()
        if user:
            if check_password_hash(user.password, form.password.data):
                if(user.flag_active):
                    login_user(user)
                elif(user.username is 'admin'):
                    login_user(user)
                else:
                    return render_template('activate.html', user=user.username), 200
                return redirect(url_for('projects'))
            else:
                session['mssg'] = "Invalid Username or Password";
                return render_template('login.html', subtitle="Login", form=form, mssg=session['mssg'])
        else:
            session['mssg'] = "Invalid Username or Password";
            return render_template('login.html', subtitle="Login", form=form, mssg=session['mssg'])
    return render_template('login.html', subtitle="Login", form=form, mssg=session['mssg']), 200


@app.route('/signup', methods=['GET', 'POST'])
def signup():
    form = SignupForm()
    session['mssg'] = ""
    if form.validate_on_submit():
        user = Users.query.filter_by(email=form.email.data).first()
        if user is None:
            hashed_pass = generate_password_hash(
                form.password.data, method='sha256')
            new_user = Users(username=form.username.data,
                             email=form.email.data, password=hashed_pass)
            # user_table = UserTableCreator(form.email.data)
            # Base.metadata.create_all(engine)
            db.session.add(new_user)
            db.session.commit()
            db.session.close()
            return redirect(url_for('login'))
        else:
            session['mssg'] = "Email ID already in use. Please login";

            return render_template('register.html', form=form, subtitle="Signup", mssg=session['mssg'])

    return render_template('register.html', subtitle="Signup", form=form, mssg=session['mssg']), 200


@app.route('/forgot', methods=['GET', 'POST'])
def forgot():
    return render_template('login.html', subtitle="Forgot"), 200


@app.route('/projects', methods=['POST', 'GET'])
@login_required
def projects():
    user = Users.query.filter_by(id=current_user.id).first()
    form = project_form()
    path_form = driver_path_form()
    project_list = Project.query.all()
    user_projects = set([x for x in project_list if user in x.users ])
    print(user_projects)
    print("Okay")
    
    if path_form.validate() and path_form.submit2.data:
        path = path_form.path.data
        current_user.meta = path
        db.session.commit()
        return redirect('projects')

    if(current_user.meta is None):
        return render_template('projects.html', form=form, projects=user_projects, mssg=session['mssg'], show_setup=True, path_form=path_form), 200
    
    if form.validate() and form.submit1.data:
        print("Imd inside")
        try:
            check_proj = Project.query.filter_by(
                name=form.name.data).filter_by().first()
            print(check_proj , form.name.data)
            if(check_proj and user in check_proj.users.all()):
                session['mssg'] = "Project {} canot be created. You already have a project with that name.".format(
                    form.name.data)
                return redirect('projects')
            else:
                new_proj = Project(name=form.name.data)
                new_proj.users.append(user)
                db.session.add(new_proj)
                db.session.commit()
                session['mssg'] = "Project {} created. Browse in the sidebar.".format(
                    form.name.data)
                return redirect('projects')
        except Exception as e:
            session['mssg'] = "Something went wrong : " + str(e)
            return redirect('projects')
    return render_template('projects.html', form=form, projects=user_projects, mssg=session['mssg'], path_form=path_form), 200

@app.route('/del_project/<id>' , methods=['POST' , 'GET'])
@login_required
def del_project(id):
    project_active = Project.query.filter_by( id = int(curr_project())).first()
    current_user.projects.remove(project_active)
    db.session.commit()
    session['mssg'] = "Project " + project_active.name + " has been removed for you. Cheers!"
    return redirect('projects')

@app.route('/user', methods=['GET', 'POST'])
@login_required
def user():
    '''
        User setup done here
        - Username
        - Email for sending
        - Delete Account
        - Reset data
        - Export data
    '''
    user = current_user.username

    return render_template('user-settings.html', user=user), 200


@login_required
def set_curr_project(setProject):

    if setProject:
        session['project'] = setProject
    else:
        sesion['project'] = 0
    return int(session['project'])

@login_required
def curr_project():
    return int(session['project'])


@login_required
def curr_proj_ins():
    return Project.query.filter_by(id=int(session['project'])).first()


@login_required
def get_projects():
    project_list = Project.query.all()
    user_projects = list([x for x in project_list if current_user in x.users])
    
    return user_projects

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@login_manager.user_loader
def load_user(user_id):
    return Users.query.get(int(user_id))


@app.route('/', methods = ['GET', 'POST'])
@login_required
def home():


        project_list = Project.query.all()
        user_projects = list([x for x in project_list if current_user in x.users ])
        c_p = curr_project()
        print(c_p)
        if (int(c_p) > 0):
            project_active = Project.query.filter_by(id = int(c_p)).first()
            global visit
            if visit is 0:
                visit = 1
                session['mssg'] = " 👋   Hello there !"
            else:
                session['mssg'] = ""
            # Show only for the current project

            con_len = len(project_active.contact)
            city_len = len(set([x.city for x in project_active.scrapers ]))

            src_len = len(project_active.scrapers)
            src_fin = db.session.query(scrape_task).filter_by(status = str(2)).count()
            src_unfin = db.session.query(scrape_task).filter_by(status = str(0)).count()
            src_run = db.session.query(scrape_task).filter_by(status = str(1)).count()
            src_curr_run = db.session.query(scrape_task).filter_by(status = str(1)).all()
            job_len = len(project_active.jobs)
            job_fin = db.session.query(job_task).filter_by(status = str(2)).count()
            job_unfin = db.session.query(job_task).filter_by(status = str(3)).count()
            job_run = db.session.query(job_task).filter_by(status = str(1)).count()
            job_curr_run = db.session.query(job_task).filter_by(status = str(1)).all()


            return render_template('dash.html', con_len = con_len, city_len = city_len, src_len = src_len, src_fin = src_fin,\
                src_unfin = src_unfin, src_run = src_run, job_len = job_len, job_fin = job_fin,\
                job_unfin = job_unfin, job_run = job_run, mssg = session['mssg'], p_list = user_projects , src_curr_run = src_curr_run ,  job_curr_run = job_curr_run), 200
        else:
            session['mssg'] = "No project selected . Redirecting to Projects page."
            return redirect('projects'), 200

@app.context_processor
def inject_project():
    if session.get('project') is None:
        session['project'] = 0
    return dict(curr_project = curr_project(), curr_project_ins = curr_proj_ins(), current_user = current_user , user_projects = get_projects())


@app.route('/update_project/<id>', methods= ['GET', 'POST'])
@login_required
def update_project_and_route(id):
    set_curr_project(id)
    return redirect(url_for('home'))

@app.route('/scheduler', methods = ['GET', 'POST'])
@login_required
def scheduler():
    return render_template('scheduler.html'), 200

@app.route('/jobs', methods = ['GET', 'POST'])
@login_required
def jobs():


    if (int(curr_project()) > 0):
        form = job_form()
        job_t_form = job_test_form()

        def_city= ('0', 'Select City')
        print(get_projects())
        form.city.choices = [def_city] + [(r.city, r.city) for r in db.session.query(scrape_task)]
        project_curr = db.session.query(Project).filter_by(id = int(curr_project())).first()
        form_group_job = job_group_form()
        form_group_job.temp_select.choices =[(r.name, r.name) for r in project_curr.template]
        # TODO create group contact assoc table for sending jobs to group
        form_group_job.group_select.choices =[(r.name, r.name) for r in db.session.query(template)]

        form.keyword.choices= [(r.keyword, r.keyword) for r in db.session.query(scrape_task.keyword).distinct(scrape_task.keyword)]
        form.campaign.choices= [(r.name, r.name) for r in project_curr.template]
        job_list = project_curr.jobs
        if form.validate_on_submit():
            city= form.city.data
            keyword= form.keyword.data
            provider = "Whatsapp"
            campaign = db.session.query(template).filter_by(name = form.campaign.data).first()
            print(campaign)
            # Check if the city and keyword already exsists ?
            check_one = db.session.query(job_task).filter_by(city = city, provider = provider, keyword = keyword).first()
            if check_one is None:
                new_job= job_task(city = city, provider = provider, status = str(0), meta = str(1), keyword = keyword, template = campaign ,project_jo = project_curr ,job_test_form =job_t_form)
                project_curr.jobs.append(new_job)
                db.session.add(new_job)
                db.session.commit()
                session['mssg'] = " 👍 Job added to list."
                return redirect('/jobs')
            else:
                session['mssg'] = " 🙃 Job already exsists. You can re-run the job from the list below , or run a new job with different parameters."
                return redirect('/jobs')
        else:
            print(form.errors)
            return render_template('jobs.html', form= form, job_list = job_list, mssg = session['mssg'] , user_projects = get_projects() , form_group_job = form_group_job , job_test_form= job_t_form), 200
    
        if job_t_form.validate_on_submit():
            pass
        else:
            print(job_t_form.errors)
            return render_template('jobs.html', form= form, job_list = job_list, mssg = session['mssg'] , user_projects = get_projects() , form_group_job = form_group_job , job_test_form= job_test_form), 200

    else:
        session['mssg'] = "No project selected . Redirecting to Projects page."
        return redirect('projects')


@app.route('/user-settings', methods = ['GET', 'POST'])
@login_required
def user_settings():
    return render_template('settings.html'), 200

@app.route('/contacts', methods = ['GET', 'POST'])
@login_required
def contacts_call():
    # contacts_list = db.session.query(contacts).all()
    if (int(curr_project()) > 0):
        form_contact_sel = contact_selector()
        form_search = contact_search()
        form_filter = contact_filter()
        form_filter_city =  set([x.city for x in db.session.query(scrape_task.city).all()])
        form_filter_keyword =  set([x.keyword for x in db.session.query(scrape_task.keyword).all()])
        form_filter_tags =  set([x.keyword for x in db.session.query(scrape_task.keyword).all()])
        contact_list = list(curr_proj_ins().contact)

        form_add_contact = add_contact()
        return render_template('contacts.html', contacts_list = contact_list,form_search= form_search, form_filter = form_filter , form_filter_city = form_filter_city , form_filter_keyword = form_filter_keyword ,form_filter_tags = form_filter_tags , form_sel = form_contact_sel , form_add_contact = form_add_contact), 200
    else:
        session['mssg'] = "No project selected . Redirecting to Projects page."
        return redirect('projects')

@app.route('/data')
def data():
    """Return server side data."""
    # defining columns
    columns = [
        ColumnDT(contacts.business_name),
        ColumnDT(contacts.city),
        ColumnDT(contacts.contact_one),
        ColumnDT(contacts.contact_two),
        ColumnDT(contacts.address),
    ]

    # defining the initial query depending on your purpose
    query = db.session.query().select_from(contacts)

    # GET parameters
    params = request.args.to_dict()

    # instantiating a DataTable for the query and table needed
    rowTable = DataTables(params, query, columns)

    # returns what is needed by DataTable
    return jsonify(rowTable.output_result())

@app.route('/contacts_filter' , methods = ['POST'])
@login_required
def contact_filter():
    if (int(curr_project()) > 0):
        return jsonify({ 'mssg' : "Okay recireved "+ str(request.json)})
    else:
        session['mssg'] = "No project selected . Redirecting to Projects page."
        return jsonify({ 'mssg' : "Else gone"+ str(request.json)})

@app.route('/task_pause', methods = ['POST'])
@login_required
def task_pause(task_id):
    # Destroys the queue and the message
    # TODO implement empty queue and save last page to meta
    pass


@app.route('/scraper', methods = ['GET', 'POST'])
@login_required
def scraper():
    form = scrape_form()
    c_p = curr_project()
    project_curr = db.session.query(Project).filter_by(id = int(c_p)).first()
    scraper_list = list(project_curr.scrapers)
    print(scraper_list)
    if (int(curr_project()) > 0):

        if form.validate_on_submit():
            city= str(form.city.data).title()
            keyword= form.keyword.data
            provider = "Justdial"
            # Check if the city and keyword already exsists ?
            check_one = db.session.query(scrape_task).filter_by(city = city, keyword = keyword, provider = provider).first()
            if check_one is None:
                new_scraper= scrape_task(city = city, keyword = keyword, provider = provider, status = str(0), meta = str(1) , project_sc = project_curr)
                project_curr.scrapers.append(new_scraper)
                db.session.add(new_scraper)
                db.session.commit()
                session['mssg'] = " 👍 Scraper added to list."

                return redirect('/scraper')
            else:
                session['mssg'] = " 🙃 Job already exsists. You can re-run the job from the list below , or run a new job with different parameters."
                return redirect('/scraper')
        return render_template('scraper.html', form= form, scraper_list = scraper_list, mssg = session['mssg']), 200
    else:
        session['mssg'] = "No project selected . Redirecting to Projects page."
        return redirect('projects')

@app.route('/push_scraper_to_queue/<task_id>', methods = ['POST', 'GET'])
@login_required
def push_scraper_to_queue(task_id):

    # Pushes the task to scraper run queue
    # Runs only one task a time
    q = get_scraper_queue()
    print(q)
    try:
        task = db.session.query(scrape_task).filter_by(id = task_id).first()
        search_data= {'city': task.city, 'keyword': task.keyword, 'page': task.meta, 'task_id': task_id, 'project' : int(curr_project()) , 'user_path' : current_user.meta}
        q = get_scraper_queue()
        q.basic_publish(
            exchange = 'amq.direct',
            routing_key = 'scraper_queue',
            body = json.dumps(search_data),
            properties = pika.BasicProperties(
                delivery_mode=2
            )
        )
        task.status = 1
        task.meta = 0
        db.session.commit()
        session['mssg'] = " 👷 Will start scraping {} for {} soon .".format()

        return redirect('/scraper')
    except Exception as e:
        mssg = "We ran into an error : " + str(e)
        print(mssg)
        return redirect('/scraper')

@app.route('/push_job_to_queue/<task_id>' , methods = ['POST' , 'GET'])
@login_required
def push_job_to_queue(task_id):

    # Pushes the task to scraper run queue 
    # Runs only one task a time 
    try:
        task = db.session.query(job_task).filter_by(id = task_id).first()
        template_set = db.session.query(template).filter_by(name =task.template.name).first()
        # some_result = db.session.query(template).filter_by(id=task.id).first().as_dict()
        customer_dict = dict((col, getattr(template_set, col)) for col in template_set.__table__.columns.keys())
        job_data = {'city' : task.city ,'meta' : task.meta , 'task_id' : task_id , 'payload' : customer_dict , 'project' : int(curr_project()), 'user_path' : current_user.meta} 
        print(job_data)
        m = get_mssg_queue()
        m.basic_publish(
            exchange='amq.direct',
            routing_key='mssg_queue',
            body=json.dumps(job_data),
            properties=pika.BasicProperties(
                delivery_mode=2
            )
        )
        task.status = 1
        db.session.commit()
        return redirect('/jobs')
    except Exception as e:
        mssg = "We ran into an error : " + str(e)
        print(mssg)
        return redirect('/jobs')

@app.route('/job/delete/<job_id>' , methods=["POST" , "GET"])
@login_required
def job_delete(job_id):
    try:
        project_active = Project.query.filter_by(id = int(curr_project())).first()
        job = db.session.query(job_task).filter_by(id= int(job_id)).first()
        project_active.jobs.remove(job)
        db.session.commit()
        session["mssg"] = "Job "+str(job_id)+" Deleted succesfully"
        return redirect('/jobs')
    except Exception as e :
        mssg = "We ran into an error : " + str(e)
        session["mssg"]
        return redirect('/jobs')

@app.route('/scraper/delete/<task_id>' , methods=["POST" , "GET"])
@login_required
def scraper_delete(task_id):
    try:
        project_active = Project.query.filter_by(id = int(curr_project())).first()
        job = db.session.query(scrape_task).filter_by(id= int(task_id)).first()
        project_active.scrapers.remove(job)
        db.session.commit()
        session["mssg"] = "Scrape Task :  "+str(task_id)+"   Deleted succesfully"
        return redirect(url_for('scraper'))
    except Exception as e :
        session["mssg"] = "We ran into an error : " + str(e)
        return redirect(url_for('scraper'))
 
@app.route('/job_results/<job_id>' , methods= ['POST' , 'GET'])
@login_required
def job_results(job_id):
    try:
        job_city = db.session.query(job_task).filter_by(id = str(job_id)).first().city
        success_all = db.session.query(contacts).filter_by(city = job_city).filter((contacts.wp_cnt == 1)).all()
        invalid_all = db.session.query(contacts).filter_by(city = job_city).filter((contacts.wp_cnt == -2)).all()
        jdnum_all = db.session.query(contacts).filter_by(city = job_city).filter((contacts.wp_cnt == 0)).all()
        unable_all = db.session.query(contacts).filter_by(city = job_city).filter((contacts.wp_cnt == -1)).all()

        # success_sent = [x if x.wp_cnt is 1 else None for x in contacts]
        # invalid_sent = [x if x.wp_cnt is -2 else None for x in contacts]
        # jd_number = [x if x.wp_cnt is 0 else None for x in contacts]
        # unable_Sent = [x if x.wp_cnt is -1 else None for x in contacts]
        
        return jsonify({'success_all' : len(success_all) , 'invalid_all' : len(invalid_all)})
    except Exception as e:
        pass
        return "Naah" + str(e)


@app.route('/src_results/<job_id>/<keyword>' , methods= ['POST' , 'GET'])
@login_required
def src_results(job_id , keyword):
    try:
        src_city = db.session.query(scrape_task).filter_by(id = str(job_id)).first().city
        success_all = db.session.query(contacts).filter_by(city = src_city).filter_by(keyword = keyword).all()
        # success_sent = [x if x.wp_cnt is 1 else None for x in contacts]
        # invalid_sent = [x if x.wp_cnt is -2 else None for x in contacts]
        # jd_number = [x if x.wp_cnt is 0 else None for x in contacts]
        # unable_Sent = [x if x.wp_cnt is -1 else None for x in contacts]
        
        return jsonify({'con_all' : len(success_all)})
    except Exception as e:
        pass
        return "Naah" + str(e)


@app.route('/task_report/<job_id>' , methods = ['POST' , 'GET'])
@login_required
def task_report(job_id):
    # Endpoint for full report for JOB and TASK Results
    # TODO for next release
    pass


UPLOAD_FOLDER = os.path.abspath('./static/images/uploads/')
ALLOWED_EXTENSIONS = set(['pdf', 'png', 'jpg', 'jpeg', 'gif'])


def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1] in ALLOWED_EXTENSIONS


@app.route('/templates' , methods = ['POST' , 'GET'])
@login_required
def templates():
    if (int(curr_project()) > 0):

        form = template_form()
        c_p = int(curr_project())
        project_active = Project.query.filter_by(id = int(c_p)).first()
        temps = project_active.template

        if form.validate_on_submit():
            if request.method == 'POST':
                file = request.files['img']
                try:
                    if file and allowed_file(file.filename):
                        filename = secure_filename(file.filename)
                        img_temp = os.path.join(UPLOAD_FOLDER, filename) 
                        file.save(img_temp)
                        name = form.name.data
                        mssg_1 = form.mssg_1.data 
                        mssg_2 = form.mssg_2.data 
                        mssg_3 = form.mssg_3.data 
                        mssg_4 = form.mssg_4.data 
                        mssg_5 = form.mssg_5.data 
                        mssg_6 = form.mssg_6.data 
                        mssg_7 = form.mssg_7.data 
                        mssg_8 = form.mssg_8.data 

                        if mssg_1 or mssg_2 or mssg_3 or mssg_4 or mssg_5 or mssg_6 or mssg_7 or mssg_8 is '' :
                            new_temp = template(name = name ,img_path = filename )
                            project_active.template.append(new_temp)
                        else:
                            new_temp = template(name = name , mssg_1 = mssg_1 , img_path = filename , mssg_2 = mssg_2 , mssg_3 = mssg_3 ,\
                                mssg_4 = mssg_4, mssg_5 = mssg_5, mssg_6 = mssg_6, mssg_7 = mssg_7 , mssg_8 = mssg_8)
                            project_active.template.append(new_temp)

                        db.session.add(new_temp)
                        db.session.commit()
                        mssg = "Template successfully added"
                        print(mssg)
                        return redirect(url_for('templates'))
                except Exception as e:
                    print(str(e))
        return render_template('templates.html' , form = form ,temps = temps) , 200
    else:
        session['mssg'] = "No project selected . Redirecting to Projects page."
        return redirect('projects')


@app.route('/del_temp/<id>' , methods=['POST' , 'GET'])
@login_required
def del_temp(id):
    try:
        temp = db.session.query(template).filter_by(id = id).first()
        c_p = int(curr_project())
        project_active = Project.query.filter_by(id = int(c_p)).first()
        project_active.template.remove(temp)
        db.session.commit()
        mssg = "Template Deleted Successfully"
        return redirect(url_for('templates'))
    except Exception as e:
        print(str(e))
        return redirect(url_for('templates')) , 200



@app.route('/jobcombo/<city>' , methods = ['POST' , 'GET'])
@login_required
def jobcombo(city):
    job_city = city
    keyword = [r.keyword for r in db.session.query(scrape_task.keyword).distinct(scrape_task.keyword).filter((scrape_task.city == str(city))).all()]
    print(keyword)
    return jsonify({'options' : keyword})


@app.route('/message/session' , methods=['POST'])
@login_required
def mssg_del():
    session['mssg'] = ""
    return jsonify({'mssg' :'Emptying session mssg' })

@app.route('/export/all' , methods=['POST' , 'GET'])
@login_required
def export_all():

    backup_folder = os.path.abspath('./backups')
    con_all = db.session.query(contacts)
    jobs = db.session.query(job_task)
    scrape = db.session.query(scrape_task)

    folder_date = datetime.datetime.now()
    folder_name = str(folder_date.strftime("%c"))
    folder_name = folder_name.replace(" " , "_").replace(":" , "-")

    try:
        backup_fol = backup_folder + '\\' + folder_name
        os.makedirs(backup_fol)
        backup_con = backup_fol +  '\\contacts.csv'
        backup_job = backup_fol +  '\\jobs.csv'
        backup_scrape = backup_fol +  '\\scrape.csv'

        with open(backup_con, 'w') as contacts_file:
            outcsv = csv.writer(contacts_file, delimiter=',',quotechar='"', quoting = csv.QUOTE_MINIMAL)

            header = contacts.__table__.columns.keys()

            outcsv.writerow(header)     

            for record in con_all.all():
                outcsv.writerow([getattr(record, c) for c in header ])
        
        with open(backup_job , 'w') as job_file:
            outcsv_j = csv.writer(job_file, delimiter=',',quotechar='"', quoting = csv.QUOTE_MINIMAL)

            header = job_task.__table__.columns.keys()

            outcsv_j.writerow(header)     

            for record in jobs.all():
                outcsv_j.writerow([getattr(record, c) for c in header ])
        
        with open(backup_scrape, 'w') as job_file:
            outcsv = csv.writer(job_file, delimiter=',',quotechar='"', quoting = csv.QUOTE_MINIMAL)

            header = scrape_task.__table__.columns.keys()

            outcsv.writerow(header)     

            for record in scrape.all():
                outcsv.writerow([getattr(record, c) for c in header ])
        
            
        session['mssg'] = "Backup successfully saved"
        return redirect(url_for('settings')) , 200
    except Exception as e:
        session['mssg'] = "Error creating backup - "+str(e)
        return redirect(url_for('settings')) , 200



@app.route('/settings' , methods=['POST' , 'GET'])
@login_required
def settings():
    if (int(curr_project()) > 0):

        form = import_file()
        if form.validate_on_submit():
            if request.method == 'POST':
                file = request.files['data_file']
                filename = secure_filename(file.filename)
                img_temp = os.path.join(UPLOAD_FOLDER, 'temp',filename) 
                file.save(img_temp)
                if 'contact' in request.form['import-con']:
                    print("in")
                    with open(img_temp, 'r') as csv_file:
                        rea = csv.reader(csv_file)
                        header = next(rea)
                        print(rea)
                        session['mssg'] = header
                else:
                    session['mssg'] = "OFF pa"
        return render_template('extra.html' , mssg = session['mssg'] , form=form) , 200
    else:
        session['mssg'] = "No project selected . Redirecting to Projects page."
        return redirect('projects')
