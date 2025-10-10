package transform

import (
	"context"

	"collections/games/magic/dataset"
)

type Transform interface {
	Transform(
		ctx context.Context,
		datasets []dataset.Dataset,
		options ...TransformOption,
	) (*TransformOutput, error)
}

type TransformOutput struct{}

type TransformOption interface {
	transformOption()
}

type OptTransformLimit struct {
	Limit int
}

type OptTransformParallel struct {
	Parallel int
}

func (o OptTransformLimit) transformOption()    {}
func (o OptTransformParallel) transformOption() {}
