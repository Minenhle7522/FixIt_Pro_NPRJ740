from django import forms
from decimal import Decimal
from .models import MaintenanceRequest, StaffNote, Feedback, Attachment, WorkLog, Material, ContractorQuotation, ContractorPayment


class MaintenanceRequestForm(forms.ModelForm):
    class Meta:
        model = MaintenanceRequest
        fields = ['title', 'description', 'category', 'priority', 'incident_at', 'photo', 'location_description', 'access_permission', 'preferred_visit_time', 'safety_risk']
        widgets = {
            'access_permission': forms.RadioSelect(),
            'preferred_visit_time': forms.Select(attrs={'class':'form-select'}),
            'safety_risk': forms.CheckboxInput(attrs={'class':'form-check-input'}),
            'incident_at': forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'),
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Brief title of the issue'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 5}),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'priority': forms.Select(attrs={'class': 'form-select'}),
            'photo': forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
            'building': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Residence/Building'}),
            'floor': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Floor'}),
            'apartment_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Apartment/Unit number'}),
            'location_description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Room, bathroom, kitchen, etc.'}),
        }

    def __init__(self, *args, **kwargs):
        self.tenant = kwargs.pop('tenant', None)
        super().__init__(*args, **kwargs)

        default_category = MaintenanceRequest._meta.get_field('category').get_default()
        default_priority = MaintenanceRequest._meta.get_field('priority').get_default()

        self.fields['incident_at'].input_formats = ['%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M:%S']
        self.fields['category'].initial = default_category
        self.fields['priority'].initial = default_priority

        if 'category' not in self.initial:
            self.initial['category'] = default_category
        if 'priority' not in self.initial:
            self.initial['priority'] = default_priority

        self.fields['incident_at'].help_text = 'When you first noticed the problem (different from the submission time).'
        self.fields['priority'].help_text = 'Your initial assessment; the landlord may adjust it after review.'

    def clean_incident_at(self):
        value = self.cleaned_data.get('incident_at')
        if value and value > __import__('django.utils.timezone', fromlist=['now']).now():
            raise forms.ValidationError('Incident time cannot be in the future.')
        return value

    def clean_photo(self):
        photo = self.cleaned_data.get('photo')
        if photo and photo.size > 5 * 1024 * 1024:
            raise forms.ValidationError('Photo must be 5 MB or smaller.')
        return photo

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.tenant = self.tenant
        instance.quotation_required = True
        lease = getattr(self, 'verified_lease', None)
        if not lease:
            raise ValueError('A verified, current lease is required to submit a maintenance request.')
        instance.lease = lease
        instance.apartment_number = lease.unit
        instance.building = lease.residence
        instance.floor = lease.floor
        instance.sla_hours = MaintenanceRequest.sla_for_priority(instance.priority)
        instance.sla_deadline = None
        if commit:
            instance.save()
        return instance


class AdminRequestUpdateForm(forms.ModelForm):
    class Meta:
        model = MaintenanceRequest
        # Assignment/status use dedicated workflow actions. Cost totals are always calculated.
        fields = ['priority', 'approved_hourly_rate', 'parts_required', 'admin_notes', 'diagnosis']
        widgets = {
            'priority': forms.Select(attrs={'class': 'form-select'}),
            'approved_hourly_rate': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
            'parts_required': forms.TextInput(attrs={'class': 'form-control'}),
            'admin_notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'diagnosis': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['approved_hourly_rate'].min_value = Decimal('0.00')
        if self.instance and self.instance.pk and self.instance.quotation_required:
            # Quotation jobs are priced by the approved quotation, so there is no hourly rate to edit.
            del self.fields['approved_hourly_rate']
        # Freeze the approved rate once work has been accepted/started/completed.
        if 'approved_hourly_rate' in self.fields and self.instance and self.instance.pk and self.instance.status in {'accepted','in_progress','awaiting_parts','completed','verified','closed'}:
            self.fields['approved_hourly_rate'].disabled = True
            self.fields['approved_hourly_rate'].help_text = 'Locked because maintenance work has already started.'


class WorkLogForm(forms.ModelForm):
    """Contractor visit / access record: whether access was gained and what work was done."""
    class Meta:
        model = WorkLog
        fields = ['access_outcome', 'notes']
        labels = {'access_outcome': 'Access outcome', 'notes': 'Work performed / reason access failed'}
        widgets = {
            'access_outcome': forms.RadioSelect(),
            'notes': forms.Textarea(attrs={
                'class': 'form-control', 'rows': 4,
                'placeholder': 'Describe the work completed and the result, or why you could not get access...'
            }),
        }

    def clean_notes(self):
        notes = (self.cleaned_data.get('notes') or '').strip()
        if len(notes) < 10:
            raise forms.ValidationError('Please provide a clear description (at least 10 characters).')
        return notes


class MaterialForm(forms.ModelForm):
    class Meta:
        model = Material
        fields = ['description', 'quantity', 'unit_cost']
        widgets = {
            'description': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Part/material description'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0.01'}),
            'unit_cost': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
        }

    def clean_quantity(self):
        value = self.cleaned_data['quantity']
        if value <= 0:
            raise forms.ValidationError('Quantity must be greater than zero.')
        return value

    def clean_unit_cost(self):
        value = self.cleaned_data['unit_cost']
        if value < 0:
            raise forms.ValidationError('Unit cost cannot be negative.')
        return value


class StaffNoteForm(forms.ModelForm):
    class Meta:
        model = StaffNote
        fields = ['note']
        widgets = {'note': forms.Textarea(attrs={'class': 'form-control', 'rows': 4})}

    def __init__(self, *args, **kwargs):
        self.request_obj = kwargs.pop('request_obj', None)
        self.staff = kwargs.pop('staff', None)
        super().__init__(*args, **kwargs)

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.request = self.request_obj
        instance.staff = self.staff
        if commit:
            instance.save()
        return instance


class FeedbackForm(forms.ModelForm):
    class Meta:
        model = Feedback
        fields = ['rating', 'comment']
        widgets = {'rating': forms.Select(attrs={'class': 'form-select'}), 'comment': forms.Textarea(attrs={'class': 'form-control', 'rows': 4})}


class AttachmentForm(forms.ModelForm):
    class Meta:
        model = Attachment
        fields = ['file', 'description']
        widgets = {'file': forms.FileInput(attrs={'class': 'form-control', 'accept': '.jpg,.jpeg,.png,.pdf'}), 'description': forms.TextInput(attrs={'class': 'form-control mt-2', 'placeholder': 'Short description of the evidence (e.g. photo after repair)'})}

    def clean_file(self):
        uploaded = self.cleaned_data.get('file')
        if uploaded:
            if uploaded.size > 10 * 1024 * 1024:
                raise forms.ValidationError('Attachment must be 10 MB or smaller.')
            ext = uploaded.name.rsplit('.', 1)[-1].lower() if '.' in uploaded.name else ''
            if ext not in {'jpg', 'jpeg', 'png', 'pdf'}:
                raise forms.ValidationError('Only JPG, JPEG, PNG or PDF attachments are allowed.')
            if ext in {'jpg', 'jpeg', 'png'}:
                # The file must really be an image, not something renamed to .jpg
                from PIL import Image
                try:
                    Image.open(uploaded).verify()
                except Exception:
                    raise forms.ValidationError('This file is not a valid image. Upload a real JPG or PNG photo.')
                finally:
                    uploaded.seek(0)
        return uploaded


class RequestFilterForm(forms.Form):
    STATUS_CHOICES = [('', 'All Statuses')] + list(MaintenanceRequest.STATUS_CHOICES)
    PRIORITY_CHOICES = [('', 'All Priorities')] + list(MaintenanceRequest.PRIORITY_CHOICES)
    CATEGORY_CHOICES = [('', 'All Categories')] + list(MaintenanceRequest.CATEGORY_CHOICES)
    status = forms.ChoiceField(choices=STATUS_CHOICES, required=False, widget=forms.Select(attrs={'class': 'form-select'}))
    priority = forms.ChoiceField(choices=PRIORITY_CHOICES, required=False, widget=forms.Select(attrs={'class': 'form-select'}))
    category = forms.ChoiceField(choices=CATEGORY_CHOICES, required=False, widget=forms.Select(attrs={'class': 'form-select'}))
    search = forms.CharField(required=False, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Search requests...'}))
    date_from = forms.DateField(required=False, widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}))
    date_to = forms.DateField(required=False, widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}))


class ContractorQuotationForm(forms.ModelForm):
    """Quotation: the labour amount IS the price. Hours are optional and informational only."""
    class Meta:
        model = ContractorQuotation
        fields = ['scope', 'labour_amount', 'estimated_materials', 'estimated_hours']
        labels = {'scope': 'Scope of work', 'labour_amount': 'Labour (R)', 'estimated_materials': 'Materials (R)',
                  'estimated_hours': 'Estimated time (hours)'}
        widgets = {'scope': forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'placeholder': 'What will you do, and what will it cover? e.g. Replace the leaking mixer tap and test for leaks.'}),
                   'labour_amount': forms.NumberInput(attrs={'class': 'form-control', 'min': '0', 'step': 'any', 'placeholder': '0.00'}),
                   'estimated_materials': forms.NumberInput(attrs={'class': 'form-control', 'min': '0', 'step': 'any', 'placeholder': '0.00'}),
                   'estimated_hours': forms.NumberInput(attrs={'class': 'form-control', 'min': '0', 'step': 'any', 'placeholder': 'Optional'})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['estimated_materials'].required = False
        self.fields['estimated_hours'].required = False
        self.fields['estimated_hours'].help_text = 'Optional, for information only. The labour amount is what you are paid.'

    def clean_scope(self):
        scope = (self.cleaned_data.get('scope') or '').strip()
        if len(scope) < 10:
            raise forms.ValidationError('Describe the work in at least 10 characters.')
        return scope

    def clean(self):
        data = super().clean()
        if data.get('estimated_materials') is None:
            data['estimated_materials'] = Decimal('0.00')
        for name in ['labour_amount', 'estimated_materials', 'estimated_hours']:
            if data.get(name) is not None and data[name] < 0:
                self.add_error(name, 'This cannot be negative.')
        labour = data.get('labour_amount')
        if labour is not None and labour + data['estimated_materials'] <= 0:
            self.add_error('labour_amount', 'The quotation total must be greater than zero.')
        return data


class ContractorPaymentForm(forms.ModelForm):
    """The amount is calculated by the system from the approved quotation; the landlord only supplies proof."""
    class Meta:
        model = ContractorPayment
        fields = ['payment_date', 'reference', 'proof']
        widgets = {'payment_date': forms.DateInput(attrs={'class':'form-control','type':'date'}),
                   'reference': forms.TextInput(attrs={'class':'form-control','placeholder':'Bank reference (optional)'}),
                   'proof': forms.FileInput(attrs={'class':'form-control','accept':'.pdf,.jpg,.jpeg,.png'})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['proof'].required = True
        self.fields['reference'].required = False
        self.fields['proof'].label = 'Proof of payment'

    def clean_proof(self):
        proof = self.cleaned_data.get('proof')
        if proof:
            import os
            if proof.size > 5 * 1024 * 1024: raise forms.ValidationError('Maximum proof size is 5 MB.')
            if os.path.splitext(proof.name)[1].lower() not in {'.pdf','.png','.jpg','.jpeg'}:
                raise forms.ValidationError('Only PDF, PNG or JPEG proof is accepted.')
        return proof
