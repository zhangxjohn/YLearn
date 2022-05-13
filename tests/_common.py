def validate_leaner(data_generator, leaner,
                    fit_kwargs=None, estimate_kwargs=None,
                    check_fitted=True, check_effect=True):
    # generate data
    data, test_data, outcome, treatment, adjustment, covariate = data_generator()

    # fit
    kwargs = {}
    if adjustment:
        kwargs['adjustment'] = adjustment
    if covariate:
        kwargs['covariate'] = covariate

    if fit_kwargs:
        kwargs.update(fit_kwargs)
    leaner.fit(data, outcome, treatment, **kwargs)
    if check_fitted:
        assert hasattr(leaner, '_is_fitted') and getattr(leaner, '_is_fitted')

    # estimate
    kwargs = dict(data=test_data, quantity=None)
    if estimate_kwargs:
        kwargs.update(estimate_kwargs)
    pred = leaner.estimate(**kwargs)
    assert pred is not None
    if check_effect:
        assert pred.min() != pred.max()