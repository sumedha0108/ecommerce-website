from flask import Flask, render_template, request, url_for, redirect, flash
from flask_bootstrap import Bootstrap5
from flask_sqlalchemy import SQLAlchemy
from flask_ckeditor import CKEditor, CKEditorField
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin, login_user, LoginManager, login_required, current_user, logout_user
from sqlalchemy.orm import relationship
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, PasswordField, SelectField, RadioField
from wtforms.validators import DataRequired, URL
from sqlalchemy import Enum
from sqlalchemy.orm.exc import NoResultFound
from dotenv import load_dotenv
import os

load_dotenv()


app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('FLASK_KEY')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///commerce.db'
db = SQLAlchemy()
db.init_app(app)

ckeditor = CKEditor(app)
Bootstrap5(app)

login_manager = LoginManager()
login_manager.init_app(app)

class AddToCartForm(FlaskForm):
    submit = SubmitField('Add to Cart')

class BuyProduct(FlaskForm):
    submit = SubmitField('Buy Now')

class PaymentForm(FlaskForm):
    payment_method = SelectField('Payment Method', choices=[('cash_on_delivery', 'Cash on Delivery'), ('online_payment', 'Online Payment')])
    submit = SubmitField('Proceed to Payment')

class CashPayForm(FlaskForm):
    name = StringField('Name')
    address = CKEditorField('Address')
    phone_number = StringField('Phone number')
    submit = SubmitField('Confirm Order')

class OnlinePayForm(FlaskForm):
    payment_done = SelectField('Is payment done?', choices = ['Yes', 'No'])
    name = StringField('Name')
    address = CKEditorField('Address')
    phone_number = StringField('Phone number')
    submit = SubmitField('Confirm Order')


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


class User(UserMixin, db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(100), unique=True)
    password = db.Column(db.String(100))
    name = db.Column(db.String(1000))
    cart_items = db.relationship('Cart_Item', back_populates='user')
    bought = db.relationship('Bought', back_populates='user')

class Product(db.Model):
    __tablename__ = "products"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    price = db.Column(db.Float, nullable=False)
    image_url = db.Column(db.String(255), nullable=True)
    cart_items = db.relationship('Cart_Item', back_populates='product')
    bought = db.relationship('Bought', back_populates='product')

class Cart_Item(db.Model):
    __tablename__ = 'carts'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=1)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    user = relationship('User', back_populates='cart_items')
    product = relationship('Product', back_populates='cart_items')

class Bought(db.Model):
    __tablename__ = 'products_bought'
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    payment_method = db.Column(db.String(100), nullable=False)
    total_amt = db.Column(db.Integer)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    user = relationship('User', back_populates='bought')
    product = relationship('Product', back_populates='bought')
    quantity = db.Column(db.Integer, nullable=False, default=1)
    status = db.Column(Enum('Delivered', 'Not Delivered', name='order_status'), default='Not Delivered')



with app.app_context():
    db.create_all()



@app.route('/')
def home():
    product = db.session.execute(db.select(Product)).scalars().all()
    return render_template('index.html', logged_in=current_user.is_authenticated, products = product)

@app.route('/cart', methods = ['POST', 'GET'])
def cart():
    form = BuyProduct()
    if form.validate_on_submit():
        return redirect(url_for('payment'))
    user_cart_items = Cart_Item.query.filter_by(user_id=current_user.id).all()
    total_price = sum(item.product.price * item.quantity for item in user_cart_items)
    return render_template('cart.html', logged_in=current_user.is_authenticated, cart_items=user_cart_items, form=form, price = total_price)

@app.route('/add-to-cart/<int:prod_id>', methods=['GET', 'POST'])
def add_cart(prod_id):
    product = db.get_or_404(Product, prod_id)
    existing_item = Cart_Item.query.filter_by(user_id=current_user.id, product_id=prod_id).first()

    if current_user.is_authenticated:

        if existing_item:
            existing_item.quantity += 1
        else:
            new_cart_item = Cart_Item(name=product.name, quantity=1, product_id=prod_id, user_id=current_user.id)
            db.session.add(new_cart_item)

        db.session.commit()
        flash(f'{product.name} added to cart successfully.')
        return redirect(url_for('cart'))
    else:
        flash('You need to log in to add items to the cart.')
        return redirect(url_for('login'))

@app.route('/update-quantity', methods=['POST', 'GET'])
@login_required
def update_quantity():
    item_id = request.form.get('item_id')
    action = request.form.get('action')
    item = db.get_or_404(Cart_Item, item_id)

    if action == 'increase':
        item.quantity += 1
    elif action == 'decrease':
        if item.quantity > 1:
            item.quantity -= 1

    db.session.commit()
    return redirect(url_for('cart'))

@app.route('/product/<int:prod_id>' ,methods = ['GET', 'POST'])
def product(prod_id):
    product = db.get_or_404(Product, prod_id)
    form = AddToCartForm()
    if form.validate_on_submit():
        return redirect(url_for('add_cart', prod_id=product.id))

    return render_template('product.html', logged_in=current_user.is_authenticated, product=product, form=form)

@app.route('/payment', methods=['GET', 'POST'])
def payment():
    form = PaymentForm()
    cart_items = Cart_Item.query.filter_by(user_id=current_user.id).all()
    total_price = sum(item.product.price * item.quantity for item in cart_items)

    if form.validate_on_submit():
        payment_method = form.payment_method.data

        if payment_method == 'cash_on_delivery':
            return redirect(url_for('cash_payment', price = total_price))
        elif payment_method == 'online_payment':
            return redirect(url_for('online_payment', price = total_price))

    return render_template('payment.html', form=form, total = total_price)

@app.route('/cash-payment', methods=['GET', 'POST'])
def cash_payment():
    form = CashPayForm()
    total_price = request.args.get('price', type=float)
    if form.validate_on_submit():
        try:
            cart_items = Cart_Item.query.filter_by(user_id=current_user.id).all()

            for cart_item in cart_items:
                new_bought_item = Bought(
                    product_id=cart_item.product_id,
                    payment_method='cash_on_delivery',
                    total_amt=(cart_item.product.price * cart_item.quantity),
                    user_id=current_user.id,
                    quantity=cart_item.quantity,
                    status='Not Delivered',
                )
                db.session.add(new_bought_item)

            Cart_Item.query.filter_by(user_id=current_user.id).delete()

            db.session.commit()

            flash('Order placed successfully. You will pay on delivery.')
            return redirect(url_for('home'))

        except NoResultFound:
            flash('No items found in the cart.')
            return redirect(url_for('home'))
    return render_template('cash.html', form=form, total = total_price)

@app.route('/online-payment', methods=['GET', 'POST'])
def online_payment():
    total_price = request.args.get('price', type=float)
    form = OnlinePayForm()
    if form.validate_on_submit():
        try:
            cart_items = Cart_Item.query.filter_by(user_id=current_user.id).all()
            if form.payment_done.data == 'Yes':
                for cart_item in cart_items:
                    new_bought_item = Bought(
                        product_id=cart_item.product_id,
                        payment_method='online_payment',
                        total_amt=(cart_item.product.price * cart_item.quantity),
                        user_id=current_user.id,
                        quantity=cart_item.quantity,
                        status='Not Delivered',
                    )
                    db.session.add(new_bought_item)

                Cart_Item.query.filter_by(user_id=current_user.id).delete()

                db.session.commit()

                flash('Order placed successfully. Thank you for your payment.')
                return redirect(url_for('home'))

            else:
                flash('Payment not completed. Please complete the payment to proceed.')

        except NoResultFound:
            flash('No items found in the cart.')
            return redirect(url_for('home'))
    return render_template('online.html', form = form, total = total_price)

@app.route('/register', methods=['POST', 'GET'])
def register():
    if request.method == 'POST':
        data = request.form
        email = request.form.get('email')
        result = db.session.execute(db.select(User).where(User.email == email))
        user = result.scalar()
        if user:
            flash("You've already signed up with that email, log in instead!")
            return redirect(url_for('login'))
        new_user = User(
            email=data['email'],
            password=generate_password_hash(data['password'], method='pbkdf2:sha256', salt_length=8),
            name=data['name']
        )
        db.session.add(new_user)
        db.session.commit()
        login_user(new_user)
        return redirect(url_for('home'))

    return render_template("register.html", logged_in=current_user.is_authenticated)


@app.route('/login', methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get('email')
        password = request.form.get('password')

        result = db.session.execute(db.select(User).where(User.email == email))
        user = result.scalar()

        if not user:
            flash("That email does not exist, please try again.")
            return redirect(url_for('login'))
        elif not check_password_hash(user.password, password):
            flash('Wrong password')
            return redirect(url_for('login'))
        else:
            login_user(user)
            return redirect(url_for('home'))
    return render_template("login.html", logged_in=current_user.is_authenticated)

@app.route('/logout')
def logout():
    logout_user()
    return render_template('index.html')


if __name__ == '__main__':
    app.run(debug=True)