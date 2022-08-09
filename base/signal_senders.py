from .models import Member

senders = {role: (Member, role) for role, _ in Member.positions}
