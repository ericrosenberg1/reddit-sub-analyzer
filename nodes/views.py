"""
Django views for volunteer nodes with input sanitization.
"""

import logging
import re
import smtplib
import ssl
from email.message import EmailMessage

from django.conf import settings
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from reddit_analyzer.middleware import InputSanitizer
from .models import VolunteerNode

logger = logging.getLogger(__name__)


def nodes_home(request):
    """List all volunteer nodes."""
    stats = VolunteerNode.get_stats()
    volunteer_nodes = list(VolunteerNode.get_active_nodes(limit=30))

    return render(request, 'nodes/index.html', {
        'node_stats': stats,
        'volunteer_nodes': volunteer_nodes,
        'nav_active': 'nodes',
    })


@require_http_methods(['GET', 'POST'])
def node_join(request):
    """Join as a volunteer node with input sanitization."""
    form_data = {
        'email': '',
        'reddit_username': '',
        'location': '',
        'system_details': '',
        'availability': '',
        'bandwidth_notes': '',
        'notes': '',
    }
    manage_link = None
    email_sent = False

    if request.method == 'POST':
        # Sanitize all inputs
        raw_email = (request.POST.get('email') or '').strip()
        sanitized_email = InputSanitizer.sanitize_email(raw_email)

        form_data = {
            'email': raw_email,  # Keep original for redisplay
            'reddit_username': InputSanitizer.sanitize_username(
                request.POST.get('reddit_username') or ''
            ),
            'location': InputSanitizer.sanitize_text(
                request.POST.get('location') or '', max_length=128
            ),
            'system_details': InputSanitizer.sanitize_text(
                request.POST.get('system_details') or '', max_length=500
            ),
            'availability': InputSanitizer.sanitize_text(
                request.POST.get('availability') or '', max_length=128
            ),
            'bandwidth_notes': InputSanitizer.sanitize_text(
                request.POST.get('bandwidth_notes') or '', max_length=128
            ),
            'notes': InputSanitizer.sanitize_text(
                request.POST.get('notes') or '', max_length=500
            ),
        }

        errors = []
        if not sanitized_email:
            errors.append("A valid contact email is required.")
        if not form_data['reddit_username']:
            errors.append("Share the Reddit account you plan to run with.")

        if errors:
            for err in errors:
                messages.error(request, err)
        else:
            try:
                node = VolunteerNode.objects.create(
                    email=sanitized_email,
                    reddit_username=form_data['reddit_username'],
                    location=form_data['location'],
                    system_details=form_data['system_details'],
                    availability=form_data['availability'],
                    bandwidth_notes=form_data['bandwidth_notes'],
                    notes=form_data['notes'],
                )
                manage_link = _build_manage_link(request, node.manage_token)
                email_sent = _send_node_email(sanitized_email, manage_link)

                if email_sent:
                    node.manage_token_sent_at = timezone.now()
                    node.save(update_fields=['manage_token_sent_at'])
                    messages.success(
                        request,
                        "Thanks for volunteering! Check your inbox for the private link."
                    )
                else:
                    messages.warning(
                        request,
                        "Thanks for volunteering! Copy the private link below to manage your node."
                    )

                form_data = {key: '' for key in form_data}
            except Exception as e:
                logger.exception("Failed to create volunteer node: %s", e)
                messages.error(request, "Failed to register node. Please try again.")

    return render(request, 'nodes/join.html', {
        'form_data': form_data,
        'manage_link': manage_link,
        'email_sent': email_sent,
        'nav_active': 'nodes',
    })


@require_http_methods(['GET', 'POST'])
def node_manage(request, token):
    """Manage a volunteer node with token validation and input sanitization."""
    # Validate token format (should be UUID-like hex string)
    if not token or not re.match(r'^[a-fA-F0-9]{32,64}$', token):
        messages.error(request, "Invalid node token.")
        return redirect('node_join')

    node = VolunteerNode.objects.filter(
        manage_token=token,
        is_deleted=False
    ).first()

    if not node:
        messages.error(request, "That node link is no longer active. Submit the join form again.")
        return redirect('node_join')

    if request.method == 'POST':
        action = request.POST.get('action', '').strip()

        if action == 'delete':
            node.soft_delete()
            messages.success(request, "Your node has been removed. Thanks for contributing!")
            return redirect('nodes_home')

        # Sanitize all inputs
        raw_email = (request.POST.get('email') or '').strip()
        sanitized_email = InputSanitizer.sanitize_email(raw_email)

        updated_username = InputSanitizer.sanitize_username(
            request.POST.get('reddit_username') or ''
        )
        updated_location = InputSanitizer.sanitize_text(
            request.POST.get('location') or '', max_length=128
        )
        updated_system = InputSanitizer.sanitize_text(
            request.POST.get('system_details') or '', max_length=500
        )
        updated_availability = InputSanitizer.sanitize_text(
            request.POST.get('availability') or '', max_length=128
        )
        updated_bandwidth = InputSanitizer.sanitize_text(
            request.POST.get('bandwidth_notes') or '', max_length=128
        )
        updated_notes = InputSanitizer.sanitize_text(
            request.POST.get('notes') or '', max_length=500
        )

        # Validate and sanitize health status
        chosen_status = request.POST.get('health_status', '').strip()
        valid_statuses = {'active', 'paused', 'pending', 'broken'}
        if chosen_status not in valid_statuses:
            chosen_status = node.health_status

        errors = []
        if not sanitized_email:
            errors.append("A valid email is required.")
        if not updated_username:
            errors.append("Your Reddit username helps coordinate API access.")

        if errors:
            for err in errors:
                messages.error(request, err)
            # Update node object for redisplay (use raw values)
            node.email = raw_email
            node.reddit_username = updated_username
            node.location = updated_location
            node.system_details = updated_system
            node.availability = updated_availability
            node.bandwidth_notes = updated_bandwidth
            node.notes = updated_notes
            node.health_status = chosen_status
        else:
            # Apply sanitized updates
            node.email = sanitized_email
            node.reddit_username = updated_username
            node.location = updated_location
            node.system_details = updated_system
            node.availability = updated_availability
            node.bandwidth_notes = updated_bandwidth
            node.notes = updated_notes

            # Handle status changes
            previous_status = node.health_status
            if chosen_status == 'broken' and previous_status != 'broken':
                node.health_status = 'broken'
                node.broken_since = timezone.now()
            elif previous_status == 'broken' and chosen_status != 'broken':
                node.health_status = chosen_status
                node.broken_since = None
            else:
                node.health_status = chosen_status

            node.last_check_in_at = timezone.now()

            try:
                node.save()
                messages.success(request, "Node details updated.")
                return redirect('node_manage', token=token)
            except Exception as e:
                logger.exception("Failed to update node: %s", e)
                messages.error(request, "Failed to save changes. Please try again.")

    manage_link = _build_manage_link(request, token)

    return render(request, 'nodes/manage.html', {
        'node': node,
        'manage_link': manage_link,
        'nav_active': 'nodes',
    })


def _normalize_username(value):
    """Normalize Reddit username by removing /u/ or u/ prefix."""
    if not value:
        return ''
    cleaned = value.strip()
    lowered = cleaned.lower()
    if lowered.startswith('/u/'):
        cleaned = cleaned[3:]
    elif lowered.startswith('u/'):
        cleaned = cleaned[2:]
    return cleaned.strip().lstrip('/')


def _build_manage_link(request, token):
    """Build the full management link URL."""
    if not token:
        return ''
    path = reverse('node_manage', kwargs={'token': token})
    if settings.SITE_URL:
        return f"{settings.SITE_URL.rstrip('/')}{path}"
    return request.build_absolute_uri(path)


def _send_node_email(recipient, manage_link):
    """Send the management link email."""
    if not recipient or not manage_link:
        return False
    if not settings.NODE_EMAIL_SENDER or not settings.NODE_EMAIL_SMTP_HOST:
        return False

    message = EmailMessage()
    sender = settings.NODE_EMAIL_SENDER
    if settings.NODE_EMAIL_SENDER_NAME:
        sender = f"{settings.NODE_EMAIL_SENDER_NAME} <{settings.NODE_EMAIL_SENDER}>"
    message['From'] = sender
    message['To'] = recipient
    message['Subject'] = 'Your Sub Search volunteer node link'
    message.set_content(
        f"Thanks for offering your machine to help grow the Sub Search dataset!\n\n"
        f"Here is your private link to manage your node:\n"
        f"{manage_link}\n\n"
        f"Use it to update hardware details, pause contributions, or delete the node entirely.\n"
        f"We keep nodes that report a broken state for 7+ days automatically cleared out each night.\n\n"
        f"- Sub Search"
    )

    try:
        with smtplib.SMTP(settings.NODE_EMAIL_SMTP_HOST, settings.NODE_EMAIL_SMTP_PORT, timeout=20) as smtp:
            if settings.NODE_EMAIL_USE_TLS:
                context = ssl.create_default_context()
                smtp.starttls(context=context)
            if settings.NODE_EMAIL_SMTP_USERNAME:
                smtp.login(settings.NODE_EMAIL_SMTP_USERNAME, settings.NODE_EMAIL_SMTP_PASSWORD)
            smtp.send_message(message)
        return True
    except Exception:
        return False
