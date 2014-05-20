.. _payments:

========================================
Setting Up Payments for Apps and Add-ons

Marketplace payments
====================

Marketplace payments require Solitude
http://solitude.readthedocs.org/en/latest/ and WebPay
http://webpay.readthedocs.org/en/latest/, two other projects to process
payments.

Both of those projects allow a degree of mocking so that they don't talk to the
real payment back-ends.

You can run solitude on stackato to avoid setting it up yourself, or use the
mocked out version at http://mock-solitude.paas.allizom.org/.

Once you've set up solitude and webpay you will need to configure the
marketplace with the host::

    SOLITUDE_HOSTS = ('http://mock-solitude.paas.allizom.org/',)

You will also want to ensure that the URL ``/mozpay/`` routes to WebPay.


.. _PayPal developer site: https://developer.paypal.com/
