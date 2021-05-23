from flask import Flask, jsonify, request
from flask_restx.namespace import ResourceRoute
from routes.algorithm import algorithm
from routes.intakeform import intakeform
from routes.timesheetform import timesheetform
from flask_restx import Api, Resource, fields
from flask_login import LoginManager, UserMixin, login_user, \
    login_required, logout_user
from flask_login import current_user
from http import HTTPStatus
from flask_cors import CORS
import psycopg2
import google_token

app = Flask(__name__)
app.register_blueprint(intakeform)
app.register_blueprint(timesheetform)
app.register_blueprint(algorithm)
CORS(app)
app.config['CORS_HEADERS'] = 'Content-Type'

# Your Google client ID, from the API "Credentials" part of the console
GOOGLE_CLIENT_ID = \
    "400000931739-oqett115tft12ja9u5lehnimqu87bebd.apps.googleusercontent.com"

app.config['GOOGLE_CLIENT_ID'] = "400000931739-oqett115tft12ja9u5lehnimqu87bebd.apps.googleusercontent.com"

# A secret key for the application.  Generate using something like
# os.urandom(24).
app.secret_key = "b'\xf2\xa5\xa3EX:\xfc:t6\xc3\x93j\xf1\x80\xddM\x03R-\xc6r\xe7Y'"

try:
    app.config['REMEMBER_COOKIE_HTTPONLY'] = True
except RuntimeError:
    pass
login = LoginManager()
login.init_app(app)
login.session_protection = 'strong'

api = Api(app=app)


# Connect to your postgres DB
conn = psycopg2.connect("dbname=slcapplication user=postgres")
# Open a cursor to perform database operations
cur = conn.cursor()

class User(UserMixin):
    """Simple User class that stores ID, name, and profile image."""
    def __init__(self, ident, name, profile_pic):
        self.id = ident
        self.name = name
        self.profile_pic = profile_pic

    def update(self, name, profile_pic):
        self.name = name
        self.profile_pic = profile_pic
# A simple user manager.  A real world application would implement the same
# interface but using a database as a backing store.  Note that this
# implementation will behave unexpectedly if the user contacts multiple
# instances of the application since it is using an in-memory store.
class UserManager(object):
    """Simple user manager class.
    Replace with something that talks to your database instead.
    """

    def __init__(self):
        self.known_users = {}

    def add_or_update_google_user(self, google_subscriber_id, name,
                                  profile_pic):
        """Add or update user profile info."""
        print("Adding user")
        if google_subscriber_id in self.known_users:
            self.known_users[google_subscriber_id].update(name, profile_pic)
        else:
            self.known_users[google_subscriber_id] = \
                User(google_subscriber_id, name, profile_pic)
        print("Length of Users, {}".format(len(self.known_users)))
        return self.known_users[google_subscriber_id]

    def lookup_user(self, google_subscriber_id):
        """Lookup user by ID.  Returns User object."""

        return self.known_users.get(google_subscriber_id)


user_manager = UserManager()

# The user loader looks up a user by their user ID, and is called by
# flask-login to get the current user from the session.  Return None
# if the user ID isn't valid.
@login.user_loader
def user_loader(user_id):
    print("When is this called?")
    return user_manager.lookup_user(user_id)


# Decorator to add CSRF protection to any mutating function.
#
# Adding this header to the client forces the browser to first do an OPTIONS
# call, determine that the origin is not allowed, and block the subsequent
# call. (Ordinarily, the call is made but the result not made available to
# the client if the origin is not allowed, but the damage is already done.)
# Checking for the presence of this header on the server side prevents
# clients from bypassing this check.
#
# Add this decorator to all mutating operations.
def csrf_protection(fn):
    """Require that the X-Requested-With header is present."""
    def protected(*args):
        if 'X-Requested-With' in request.headers:
            return fn(*args)
        else:
            print("This is missing?")
            return "X-Requested-With header missing", HTTPStatus.FORBIDDEN
    return protected


@api.route("/me")
class Me(Resource):
    """The currently logged-in user.
    GET will return information about the user if a session exists.
    POST will login a user given an ID token, and set a session cookie.
    DELETE will log out the currently logged-in user.
    """

    a_user = api.model("User", {
        'google_id': fields.Integer(
            description="The user's Google account ID"),
        'name': fields.String(description="The user's full name"),
        'picture': fields.Url(description="A URL to the profile image"),
    })

    @login_required
    @api.response(HTTPStatus.OK, 'Success', a_user)
    def get(self):
        print("Get request called")
        print(current_user.name)
        before_return = jsonify({
            'google_id': current_user.id,
            'name': current_user.name,
            'picture': current_user.profile_pic
        })
        return before_return

    @api.param(
        'id_token', 'A JWT from the Google Sign-In SDK to be validated',
        _in='formData')
    @api.response(HTTPStatus.OK, 'Success', a_user)
    @api.response(HTTPStatus.FORBIDDEN, "Unauthorized")
    @csrf_protection
    def post(self):
        print("CALLED?")
        # Validate the identity
        id_token = request.form.get('id_token')
        print(id_token)
        if id_token is None:
            print("CASE 1")
            return "No ID token provided", HTTPStatus.FORBIDDEN

        try:
            print(app.config['GOOGLE_CLIENT_ID'])
            identity = google_token.validate_id_token(
                id_token, app.config['GOOGLE_CLIENT_ID'])
        except ValueError:
            print("CASE 2")
            return 'Invalid ID token', HTTPStatus.FORBIDDEN

        # Get the user info out of the validated identity
        if ('sub' not in identity or
                'name' not in identity or
                'picture' not in identity):
            print("CASE 3")
            return "Unexcpected authorization response", HTTPStatus.FORBIDDEN

        # This just adds a new user that hasn't been seen before and assumes it
        # will work, but you could extend the logic to do something different
        # (such as only allow known users, or somehow mark a user as new so
        # your frontend can collect extra profile information).
        print(identity['sub'])
        print(identity['name'])
        print(identity['picture'])
        user = user_manager.add_or_update_google_user(
                identity['sub'], identity['name'], identity['picture'])

        # Authorize the user:
        login_user(user, remember=True)
        print("User is authorizeed and should be logged in?")
        print("User Test: {}".format(user))

        return self.get()

    @login_required
    @api.response(HTTPStatus.NO_CONTENT, "Success")
    @csrf_protection
    def delete(self):
        logout_user()
        return "", HTTPStatus.NO_CONTENT

@api.route('/test')
class Index(Resource):
    def get(self):
        print("Test function called")
        # Execute a query
        cur.execute("SELECT * FROM formmang")

        # Retrieve query results
        records = cur.fetchall()
        print(records)
        return {"Test":"Hello World!"}


if __name__ == '__main__': 
  app.run(debug=True, host='0.0.0.0')

