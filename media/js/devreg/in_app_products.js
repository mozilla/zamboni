(function () {
    function PricePointFormatter() {
        var rowTemplateSelector = '#in-app-product-row-template';
        var rowTemplate = $(rowTemplateSelector).html();
        var $options = $(rowTemplate).find('select[name="price_id"]')
                                     .children();
        var pricePoints = Array.prototype.reduce.call(
            $options, makePrices, {});

        this.format = function (price_id) {
            return pricePoints[price_id];
        };

        function makePrices(prices, option) {
            prices[option.value] = option.textContent;
            return prices;
        }
    }
    var pricePointFormatter = new PricePointFormatter().format;

    var InlineTextComponent = flight.component(function () {
        this.defaultAttrs({
            dataSource: null,
            name: null,
            outputFormatter: function (value) { return value; },
        });

        this.setValue = function (value) {
            $.when(this.attr.outputFormatter(value))
             .done((function (newValue) {
                this.$node.text(newValue);
            }).bind(this));
        };

        this.after('initialize', function () {
            this.attr.dataSource.on('dataChange', (function (e, data) {
                this.setValue(data[this.attr.name]);
            }).bind(this));
        });
    });

    var InlineTextEditComponent = flight.component(function () {
        this.defaultAttrs({
            name: null,
            outputSelector: 'span.inline-view',
            inputSelector: 'input[type="text"]',
            errorSelector: '.field-error',
            editingClass: 'editing',
            startEditing: false,
            outputFormatter: function (value) { return value; },
            getInputValue: function (input) { return input.val(); },
        });

        this.setValue = function (value) {
            if (this.value != value) {
                this.value = value;
                this.data[this.name] = this.value;
                this.input.val(value);
                this.trigger('dataInlineEditChanged', {
                    name: this.name,
                    value: value,
                });
                this.trigger('dataChange', this.data);
            }
        };

        this.after('initialize', function () {
            this.name = this.attr.name;
            this.output = this.select('outputSelector');
            this.input = this.select('inputSelector');
            this.error = this.select('errorSelector');
            this.displayComponent = InlineTextComponent.attachTo(this.output, {
                name: this.name,
                outputFormatter: this.attr.outputFormatter,
                dataSource: this,
            });
            this.data = {};

            if (typeof this.attr.value === 'undefined') {
                this.attr.value = this.attr.getInputValue(this.input) ||
                                  this.output.text();
            }

            this.on('dataInlineEditChanged', function (e, payload) {
                this.setValue(payload.value);
                this.error.text('');
            });

            this.on('uiStartInlineEdit', function () {
                this.$node.addClass(this.attr.editingClass);
                this.input.focus();
            });

            this.on('uiDoneInlineEdit', function () {
                this.$node.removeClass(this.attr.editingClass);
            });

            this.on('dataErrors', function (e, payload) {
                e.stopPropagation();
                this.error.text(payload.errors[0]);
            });

            this.on(this.input, 'keyup', function (e) {
                this.setValue(this.attr.getInputValue(this.input));

            });

            this.on(this.input, 'change', function (e) {
                this.setValue(this.attr.getInputValue(this.input));
            });

            if (this.attr.startEditing) {
                this.trigger('uiStartInlineEdit');
            }

            this.setValue(this.attr.value);
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
            activeSelector: '.in-app-product-active',
            saveSelector: '.in-app-product-save',
            editSelector: '.in-app-product-edit',
            deleteSelector: '.in-app-product-delete',
            productIdSelector: '.in-app-product-guid',
            errorSelector: '.in-app-product-error',
        });

        this.url = function () {
            var url;
            if (this.product.guid) {
                url = format(this.detailUrlFormat, {guid: this.product.guid});
            } else {
                url = this.listUrl;
            }
            return url;
        };

        this.save = function () {
            var self = this;
            self.error.text('');
            self.saveButton.attr('disabled', true);
            var method = self.product.guid ? 'patch' : 'post';
            console.log('saving product', method.toUpperCase(), self.url(),
                        self.product);

            // TODO: pass a real localized name when bug 1070120 is fixed.
            console.warn('temporarily overriding localized name data');
            var localizedName = {};
            localizedName[this.$rootData.activeLang] = this.product.name;
            this.product.name = localizedName;
            this.product.default_locale = this.$rootData.activeLang;

            $.ajax({
                method: method,
                url: self.url(),
                data: JSON.stringify(self.product),
                contentType: 'application/json',
            }).always(function () {
                self.saveButton.attr('disabled', false);
            }).done(function (product) {
                self.product = product;
                self.trigger('uiDoneInlineEdit');
                console.log('product saved', self.product);
            }).fail(function (response) {
                console.log('failed to save product', self.product);
                var fieldErrors = response.responseJSON;
                if (fieldErrors) {
                    Object.keys(fieldErrors).forEach(function (field) {
                        self.components[field].trigger(
                            'dataErrors', {errors: fieldErrors[field]});
                    });
                } else {
                    self.trigger('dataErrors',
                        {errors: [response.responseText]});
                }
            });
        };

        this.after('initialize', function () {
            this.$rootData = $('#in-app-products').data();
            this.listUrl = this.$rootData.listUrl;
            this.detailUrlFormat = decodeURIComponent(
                this.$rootData.detailUrlFormat);
            this.name = this.select('nameSelector');
            this.price = this.select('priceSelector');
            this.guid = this.select('productIdSelector');
            this.logoUrl = this.select('logoUrlSelector');
            this.active = this.select('activeSelector');
            this.saveButton = this.select('saveSelector');
            this.editButton = this.select('editSelector');
            this.error = this.select('errorSelector');
            this.product = {
                guid: this.guid.text().trim(),
            };
            this.components = {
                logo_url: this.logoUrl,
                name: this.name,
                guid: this.guid,
                price_id: this.price,
                active: this.active,
            };

            this.on('dataInlineEditChanged', function (e, payload) {
                this.product[payload.name] = payload.value;
            });

            this.on('uiSaveRequested', function (e) {
                this.save();
            });

            this.on('uiStartInlineEdit', function () {
                this.$node.addClass('editing');
            });

            this.on('uiDoneInlineEdit', function () {
                this.$node.removeClass('editing');
                this.trigger('dataChange', this.product);
            });

            this.on(this.saveButton, 'click', function (e) {
                this.trigger('uiSaveRequested');
            });

            this.on(this.editButton, 'click', function (e) {
                this.trigger('uiStartInlineEdit');
            });

            this.on('dataErrors', function (e, payload) {
                this.error.text(payload.errors[0]);
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
            InlineTextComponent.attachTo(this.guid, {
                name: 'guid',
                dataSource: this,
            });
            InlineTextEditComponent.attachTo(this.active, {
                name: 'active',
                inputSelector: 'input[type="checkbox"]',
                startEditing: this.attr.startEditing,
                getInputValue: function (input) {
                    return input.is(':checked');
                },
                outputFormatter: function (value) {
                    if (value) {
                        return gettext('Enabled');
                    } else {
                        return gettext('Disabled');
                    }
                },
            });

            this.on(this.logoUrl, 'click', function (e) {
                if (this.$node.hasClass('editing')) {
                    var url = prompt('Please enter your logo\'s URL.');
                    this.logoUrl.siblings('.field-error').text('');
                    this.trigger('dataInlineEditChanged', {
                        name: 'logo_url',
                        value: url,
                    });
                    this.logoUrl.attr('src', url);
                }
            });

            this.on(this.logoUrl, 'dataErrors', function (e, payload) {
                e.stopPropagation();
                this.logoUrl.siblings('.field-error').text(payload.errors[0]);
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
    $('#add-in-app-product').on('click', function () {
        $('#in-app-products').removeClass('empty');
    });
})();
