(function () {
    function PricePointFormatter() {
        // A mapping from PricePointId to FormattedPriceDeferred.
        var pricePoints = {};

        var pricePointUrl = function (id) {
            return format('/api/v1/webpay/prices/{id}/', {id: id});
        }

        var priceForCurrencyCode = function (prices, currencyCode) {
            var price = _.find(prices, function (price) {
                return price.currency === currencyCode;
            });
            return [price.price, price.currency].join(' ');
        }

        this.format = function (id) {
            if (id && !pricePoints.hasOwnProperty(id)) {
                // This uses `then` because it returns a modified promise. Do
                // not change it to `done`, it will stop working.
                pricePoints[id] = $.get(pricePointUrl(id))
                                   .then(function (pricePoint) {
                    return priceForCurrencyCode(pricePoint.prices, 'USD');
                });
            }
            return pricePoints[id];
        }
    }
    var pricePointFormatter = new PricePointFormatter().format;

    var InlineTextEditComponent = flight.component(function () {
        this.defaultAttrs({
            name: null,
            outputSelector: 'span',
            inputSelector: 'input[type="text"]',
            editingClass: 'editing',
            startEditing: false,
            outputFormatter: function (value) { return value; },
        });

        this.setValue = function (value) {
            this.value = value;
            $.when(this.attr.outputFormatter(value))
             .done((function (newValue) {
                this.output.text(newValue);
            }).bind(this));
            this.input.val(value);
        };

        this.valueChanged = function (value) {
            if (this.value != value) {
                this.trigger('dataInlineEditChanged', {
                    name: this.name,
                    value: value,
                });
            }
        };

        this.after('initialize', function () {
            this.name = this.attr.name;
            this.output = this.select('outputSelector');
            this.input = this.select('inputSelector');

            if (typeof this.attr.value === 'undefined') {
                this.attr.value = this.input.val() || this.output.text();
            }

            this.on('dataInlineEditChanged', function (e, payload) {
                this.setValue(payload.value);
            });

            this.on('uiStartInlineEdit', function () {
                this.$node.addClass(this.attr.editingClass);
                this.input.focus();
            });

            this.on('uiDoneInlineEdit', function () {
                this.$node.removeClass(this.attr.editingClass);
            });

            switch (this.input.prop('tagName')) {
                case 'INPUT':
                    this.on(this.input, 'keyup', function (e) {
                        this.valueChanged(e.target.value);

                    });
                    break;
                case 'SELECT':
                    this.on(this.input, 'change', function (e) {
                        this.valueChanged(e.target.value);
                    });
                    break;
            }

            if (this.attr.startEditing) {
                this.trigger('uiStartInlineEdit');
            }

            this.valueChanged(this.attr.value);
        });
    });

    var AddInAppProductRow = flight.component(function () {
        this.defaultAttrs({
            component: null,
            componentAttrs: {},
            source: '#in-app-product-row-template',
            destination: '#in-app-products tbody',
        });

        this.after('initialize', function () {
            this.template = $(this.attr.source).html();
            this.destination = $(this.attr.destination);
            this.on('click', function () {
                this.destination.append(this.template);
                this.attr.component.attachTo(
                    this.destination.children().last(),
                    this.attr.componentAttrs);
            });
        });
    });

    var InAppProductComponent = flight.component(function () {
        this.defaultAttrs({
            startEditing: false,
            nameSelector: '.in-app-product-name',
            priceSelector: '.in-app-product-price',
            logoUrlSelector: '.in-app-product-logo-url',
            saveSelector: '.in-app-product-save',
            editSelector: '.in-app-product-edit',
            deleteSelector: '.in-app-product-delete',
            productIdSelector: '.in-app-product-id',
        });

        this.url = function () {
            var url;
            if (this.product.id) {
                url = format(this.detailUrlFormat, {id: this.product.id});
            } else {
                url = this.listUrl;
            }
            // FIXME: This is bad.
            var user = localStorage.getItem('0::user');
            if (user) {
                url += '?_user=' + user;
            }
            return url;
        };

        this.save = function () {
            this.saveButton.attr('disabled', true);
            var method = this.product.id ? 'put' : 'post';
            console.log('saving product', method.toUpperCase(), this.url(),
                        this.product);
            $.ajax({
                method: method,
                url: this.url(),
                data: this.product,
            }).always((function () {
                this.saveButton.attr('disabled', false);
            }).bind(this)).done((function (product) {
                this.product = product;
                this.trigger('uiDoneInlineEdit');
                console.log('product saved', this.product);
            }).bind(this)).fail((function () {
                console.log('failed to save product', this.product);
                alert('Error while saving product, please try again.');
            }).bind(this));
        };

        this.after('initialize', function () {
            this.$rootData = $('#in-app-products').data();
            this.listUrl = this.$rootData.listUrl;
            this.detailUrlFormat = decodeURIComponent(this.$rootData.detailUrlFormat);
            this.name = this.select('nameSelector');
            this.price = this.select('priceSelector');
            this.logoUrl = this.select('logoUrlSelector');
            this.saveButton = this.select('saveSelector');
            this.editButton = this.select('editSelector');
            this.product = {
                id: this.select('productIdSelector').val(),
            };

            this.on('dataInlineEditChanged', function (e, payload) {
                this.product[payload.name] = payload.value;
            });

            this.on('uiSaveRequested', function (e) {
                this.save();
            });

            this.on('uiStartInlineEdit', function () {
                this.$node.addClass('editing');
            })

            this.on('uiDoneInlineEdit', function () {
                this.$node.removeClass('editing');
            })

            this.on(this.saveButton, 'click', function (e) {
                this.trigger('uiSaveRequested');
            });

            this.on(this.editButton, 'click', function (e) {
                this.trigger('uiStartInlineEdit');
            });

            InlineTextEditComponent.attachTo(this.price, {
                name: 'price_id',
                inputSelector: 'select',
                startEditing: this.attr.startEditing,
                outputFormatter: pricePointFormatter,
            });
            InlineTextEditComponent.attachTo(this.name, {
                name: 'name',
                startEditing: this.attr.startEditing,
            });

            this.on(this.logoUrl, 'click', function (e) {
                if (this.$node.hasClass('editing')) {
                    var url = prompt('Please enter your logo\'s URL.');
                    this.trigger('dataInlineEditChanged', {
                        name: 'logo_url',
                        value: url,
                    });
                    this.logoUrl.attr('src', url);
                }
            });

            if (this.attr.startEditing) {
                this.trigger('uiStartInlineEdit');
            }
        });
    });

    InAppProductComponent.attachTo('.in-app-product-row');
    AddInAppProductRow.attachTo('#add-in-app-product', {
        component: InAppProductComponent,
        componentAttrs: {startEditing: true},
    });
})();
