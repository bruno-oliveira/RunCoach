"""External integration services (Intervals.icu, FIT).

Import implementations from their own modules —
``app.infrastructure.integrations.intervals_service``,
``app.infrastructure.integrations.fit_service``.

This package used to re-export ``FitService`` through a ``__getattr__`` shim, but
the class is ``FITService``, so the shim could only ever raise ``ImportError``,
and nothing imported the alias anyway. Removed rather than corrected: a lazy
second name for a class nobody reaches for is a name waiting to disagree with the
first one.
"""
