from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ObjectDoesNotExist
from django.shortcuts import render, get_object_or_404, redirect
from django.views.generic import ListView, DetailView, View
from django.utils import timezone
from .models import Item, Order, OrderItem, Address, Payment, Coupon, Refund, UserProfile
from .forms import CheckoutForm, CouponForm, RefundForm, PaymentForm

import stripe
stripe.api_key = settings.STRIPE_SECRET_KEY

import random
import string


def create_ref_code():
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=20))


def is_valid_form(values):
    print(values)
    valid = True
    for field in values:
        if field == '':
            valid = False
    return valid




class HomeView(ListView):
    model = Item
    paginate_by = 10
    template_name = 'home-page.html'


class ItemDetailView(DetailView):
    model = Item
    template_name = 'product-page.html'


class OrderSummaryView(LoginRequiredMixin, View):
    def get(self, *args, **kwargs):
        try:
            order = Order.objects.get(user=self.request.user, ordered=False)
            context = {'object': order}
            return render(self.request, 'order_summary.html', context)
        except ObjectDoesNotExist:
            messages.warning(self.request, 'You do not have an active order')
            return redirect('/')


class CheckoutView(View):
    def get(self, *args, **kwargs):
        try:
            order = Order.objects.get(user=self.request.user, ordered=False)
            form = CheckoutForm()
            context = {'form': form, 'order': order, 'couponform': CouponForm(), 'DISPLAY_COUPON_FORM': True}
            shipping_address_qs = Address.objects.filter(user=self.request.user, address_type='S', default=True)
            if shipping_address_qs.exists():
                context.update({'default_shipping_address': shipping_address_qs[0]})

            billing_address_qs = Address.objects.filter(user=self.request.user, address_type='B', default=True)
            if billing_address_qs.exists():
                context.update({'default_billing_address': billing_address_qs[0]})

            return render(self.request, 'checkout-page.html', context=context)
        except ObjectDoesNotExist:
            messages.info(self.request, "You do not have an active order")
            return redirect('core:checkout')


    def post(self, *args, **kwargs):
        form = CheckoutForm(self.request.POST or None)
        try:
            order = Order.objects.get(user=self.request.user, ordered=False)
            if form.is_valid():
                use_default_shipping = form.cleaned_data['use_default_shipping']
                if use_default_shipping:
                    shipping_address_qs = Address.objects.filter(user=self.request.user, address_type='S', default=True)
                    if shipping_address_qs.exists():
                        shipping_address = shipping_address_qs[0]
                        order.shipping_address = shipping_address
                        order.save()
                    else:
                        messages.info(self.request, 'No default shipping address available')
                        return redirect('core:checkout')
                else:
                    print(form.cleaned_data)
                    shipping_address1 = form.cleaned_data['shipping_address']
                    shipping_address2 = form.cleaned_data['shipping_address2']
                    shipping_country = form.cleaned_data['shipping_country']
                    shipping_zip = form.cleaned_data['shipping_zip']
                    # TODO functionality for commented out
                    # same_shipping_address = form.cleaned_data['same_shipping_address']
                    # save_info = form.cleaned_data['save_info']
                    if is_valid_form([shipping_address1, shipping_country, shipping_zip]):

                        shipping_address = Address(user=self.request.user, apartment_address=shipping_address2,
                                                  street_address=shipping_address1,
                                                  country=shipping_country, zip=shipping_zip, address_type='S')
                        shipping_address.save()
                        order.shipping_address = shipping_address
                        order.save()
                        set_default_shipping = form.cleaned_data['set_default_shipping']
                        if set_default_shipping:
                            shipping_address.default = True
                            shipping_address.save()

                    else:
                        messages.info(self.request, 'Please fill in required shipping address fields')
                        return redirect('core:checkout')

                use_default_billing = form.cleaned_data['use_default_billing']
                same_billing_address = form.cleaned_data['same_billing_address']
                if same_billing_address:
                    billing_address = shipping_address
                    billing_address.pk = None
                    billing_address.save()
                    billing_address.address_type = 'B'
                    billing_address.save()
                    order.billing_address = billing_address
                    order.save()

                elif use_default_billing:
                    billing_address_qs = Address.objects.filter(user=self.request.user, address_type='B', default=True)
                    if billing_address_qs.exists():
                        billing_address = billing_address_qs[0]
                        order.billing_address = billing_address
                        order.save()
                    else:
                        messages.info(self.request, 'No default billing address available')
                        return redirect('core:checkout')
                else:

                    billing_address1 = form.cleaned_data['billing_address']
                    billing_address2 = form.cleaned_data['billing_address2']
                    billing_country = form.cleaned_data['billing_country']
                    billing_zip = form.cleaned_data['billing_zip']
                    # TODO functionality for commented out
                    # same_billing_address = form.cleaned_data['same_billing_address']
                    # save_info = form.cleaned_data['save_info']
                    if is_valid_form([billing_address1, billing_country, billing_zip]):

                        billing_address = Address(user=self.request.user, apartment_address=billing_address2,
                                                   street_address=billing_address1,
                                                   country=billing_country, zip=billing_zip, address_type='B')
                        billing_address.save()
                        order.billing_address = billing_address
                        order.save()
                        set_default_billing = form.cleaned_data['set_default_billing']
                        if set_default_billing:
                            billing_address.default = True
                            billing_address.save()

                    else:
                        messages.info(self.request, 'Please fill in required billing address fields')
                payment_option = form.cleaned_data['payment_option']

                if payment_option == 'S':
                    return redirect('core:payment', payment_option='stripe')
                elif payment_option == 'P':
                    return redirect('core:payment', payment_option='paypal')
                else:
                    messages.warning(self.request, 'Invalid payment option choice')
                    return redirect('core:checkout')
        except ObjectDoesNotExist:
            messages.warning(self.request, 'You do not have an active order')
            return redirect('core:order-summary')


class PaymentView(View):

    def get(self, *args, **kwargs):
        order = Order.objects.get(user=self.request.user, ordered=False)
        if order.billing_address:
            context = {'order': order, 'DISPLAY_COUPON_FORM': False}
            userprofile = self.request.user.userprofile
            if userprofile.one_click_purchasing:
                # fetch the users card list
                cards = stripe.Customer.list_sources(
                    userprofile.stripe_customer_id,
                    limit=3,
                    object='card'
                )
                card_list = cards['data']
                if len(card_list) > 0:
                    # update the context with the default card
                    context.update({
                        'card': card_list[0]
                    })
            return render(self.request, 'payment.html', context=context)
        else:
            messages.warning(self.request, 'You have not added a billing address')
            return redirect('core:checkout')

    def post(self, *args, **kwargs):
        order = Order.objects.get(user=self.request.user, ordered=False)
        # token = self.request.POST.get('stripeToken')
        # if not token:
        #     token = 'tok_visa'
        # amount = int(order.get_total() * 100),  # as in cents
        # amount = amount[0]  # returns a tuple with number inside
        # try:
        #     charge = stripe.Charge.create(
        #         amount=amount,
        #         currency='usd',
        #         source='tok_visa',)
        #
        #     payment = Payment()
        #     payment.stripe_charge_id = charge['id']
        #     payment.user = self.request.user
        #     payment.amount = order.get_total()
        #     payment.save()

        form = PaymentForm(self.request.POST)
        userprofile = UserProfile.objects.get(user=self.request.user)
        if form.is_valid():
            token = form.cleaned_data.get('stripeToken')
            save = form.cleaned_data.get('save')
            use_default = form.cleaned_data.get('use_default')


            # Assign payment to order
            # order_items = order.items.all()
            # order_items.update(ordered=True) # Update all items in order to ordered = True
            #
            # for item in order_items:
            #     item.save()  # Have to save each item to db

            if save:
                if userprofile.stripe_customer_id != '' and userprofile.stripe_customer_id is not None:
                    customer = stripe.Customer.retrieve(
                        userprofile.stripe_customer_id)
                    customer.sources.create(source=token)

            # order.ordered = True
            # order.payment = payment
            # order.ref_code = create_ref_code()
            # order.save()

                else:
                    customer = stripe.Customer.create(
                        email=self.request.user.email,
                    )
                    customer.sources.create(source=token)
                    userprofile.stripe_customer_id = customer['id']
                    userprofile.one_click_purchasing = True
                    userprofile.save()

            amount = int(order.get_total() * 100)
            amount = amount[0]
            try:

                if use_default or save:
                    # charge the customer because we cannot charge the token more than once
                    charge = stripe.Charge.create(
                        amount=amount,  # cents
                        currency="usd",
                        customer=userprofile.stripe_customer_id
                    )
                else:
                    # charge once off on the token
                    charge = stripe.Charge.create(
                        amount=amount,  # cents
                        currency="usd",
                        source=token
                )

                payment = Payment()
                payment.stripe_charge_id = charge['id']
                payment.user = self.request.user
                payment.amount = order.get_total()
                payment.save()

                order_items = order.items.all()
                order_items.update(ordered=True)
                for item in order_items:
                    item.save()

                order.ordered = True
                order.payment = payment
                order.ref_code = create_ref_code()
                order.save()

                messages.success(self.request, "Your order was successful!")
                return redirect("/")

            except stripe.error.CardError as e:
                body = e.json_body
                err = body.get('error', {})
                messages.warning(self.request, f"{err.get('message')}")
                return redirect("/")

            except stripe.error.RateLimitError as e:
                # Too many requests made to the API too quickly
                messages.warning(self.request, "Rate limit error")
                return redirect("/")

            except stripe.error.InvalidRequestError as e:
                # Invalid parameters were supplied to Stripe's API
                print(e)
                messages.warning(self.request, "Invalid parameters")
                return redirect("/")

            except stripe.error.AuthenticationError as e:
                # Authentication with Stripe's API failed
                # (maybe you changed API keys recently)
                messages.warning(self.request, "Not authenticated")
                return redirect("/")

            except stripe.error.APIConnectionError as e:
                # Network communication with Stripe failed
                messages.warning(self.request, "Network error")
                return redirect("/")

            except stripe.error.StripeError as e:
                # Display a very generic error to the user, and maybe send
                # yourself an email
                messages.warning(
                    self.request, "Something went wrong. You were not charged. Please try again.")
                return redirect("/")

            except Exception as e:
                # send an email to ourselves
                messages.warning(
                    self.request, "A serious error occurred. We have been notifed.")
                return redirect("/")

        messages.warning(self.request, "Invalid data received")
        return redirect("/payment/stripe/")







# def product_page(request):
#     context = {}
#     return render(request, 'product-page.html', context)


@login_required
def add_to_cart(request, slug):
    item = get_object_or_404(Item, slug=slug)
    order_item, created = OrderItem.objects.get_or_create(item=item, user=request.user, ordered=False)
    order_qs = Order.objects.filter(user=request.user, ordered=False)
    if order_qs.exists():
        order = order_qs[0]
        # check if order item in order
        if order.items.filter(item__slug=item.slug).exists():
            order_item.quantity += 1
            order_item.save()
            messages.info(request, "This item quanity was changed")
            return redirect('core:order-summary')
        else:
            messages.info(request, "This item was added to your cart")
            order.items.add(order_item)
            return redirect('core:order-summary')

    else:
        ordered_date = timezone.now()
        order = Order.objects.create(user=request.user, ordered_date=ordered_date)
        messages.info(request, "This item was added to your cart")
        order.items.add(order_item)
        return redirect('core:order-summary')


@login_required
def remove_from_cart(request, slug):
    item = get_object_or_404(Item, slug=slug)
    order_qs = Order.objects.filter(user=request.user, ordered=False)
    if order_qs.exists():
        order = order_qs[0]
        # check if order item in order
        if order.items.filter(item__slug=item.slug).exists():
            order_item = OrderItem.objects.filter(item=item, user=request.user, ordered=False)[0]
            order.items.remove(order_item)
            messages.info(request, "This item was removed from your cart")
            return redirect('core:order-summary')
        else:
            messages.info(request, "This item was not in your cart")
            return redirect('core:products', slug=slug)
    else:
        messages.info(request, "You do not have an order")
        return redirect('core:products', slug=slug)


@login_required
def remove_single_item_from_cart(request, slug):
    item = get_object_or_404(Item, slug=slug)
    order_qs = Order.objects.filter(user=request.user, ordered=False)
    if order_qs.exists():
        order = order_qs[0]
        # check if order item in order
        if order.items.filter(item__slug=item.slug).exists():
            order_item = OrderItem.objects.filter(item=item, user=request.user, ordered=False)[0]
            if order_item.quantity <= 1:
                order.items.remove(order_item)
                messages.info(request, "This item was removed from your cart")
                return redirect('core:order-summary')
            order_item.quantity -= 1
            order_item.save()
            messages.info(request, "This item quantity was updated.")
            return redirect('core:order-summary')
        else:
            messages.info(request, "This item was not in your cart")
            return redirect('core:products', slug=slug)
    else:
        messages.info(request, "You do not have an order")
        return redirect('core:products', slug=slug)


def get_coupon(request, code):
    try:
        coupon = Coupon.objects.get(code=code)
        return coupon
    except ObjectDoesNotExist:
        messages.info(request, "This coupon does not exist")
        return redirect('core:checkout')


class AddCouponView(View):

    def post(self, *args, **kwargs):
        form = CouponForm(self.request.POST or None)
        if form.is_valid():
            try:
                order = Order.objects.get(user=self.request.user, ordered=False)
                code = form.cleaned_data.get('code')
                coupon = get_coupon(request=self.request, code=code)
                order.coupon = coupon
                order.save()
                messages.success(self.request, 'Successfully added coupon')
                return redirect('core:checkout')

            except ObjectDoesNotExist:
                messages.info(self.request, "You do not have an active order")
                return redirect('core:checkout')

class RequestRefundView(View):

    def get(self, *args, **kwargs):
        context = {'form': RefundForm()}
        return render(self.request, 'request-refund.html', context=context)

    def post(self, *args, **kwargs):
        form = RefundForm(self.request.POST)
        if form.is_valid():
            ref_code = form.cleaned_data.get('ref_code')
            message = form.cleaned_data.get('message')
            email = form.cleaned_data.get('email')
            # edit order
            try:
                order = Order.objects.get(ref_code=ref_code)
                order.refund_requested = True
                order.save()

                refund = Refund()
                refund.order = order
                refund.reason = message
                refund.email = email
                refund.save()
                messages.info(self.request, 'Your refund was received')
                return redirect('core:request-refund')

            except ObjectDoesNotExist:
                messages.info(self.request, 'This order does not r=exist')
                return redirect('core:request-refund')


