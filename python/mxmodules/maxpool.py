'''
@author: Sebastian Lapuschkin
@author: Gregoire Montavon
@author: Maximilian Kohlbrenner
@maintainer: Sebastian Lapuschkin
@contact: sebastian.lapuschkin@hhi.fraunhofer.de, wojciech.samek@hhi.fraunhofer.de
@date: 20.10.2015
@version: 1.2+
@copyright: Copyright (c)  2015-2017, Sebastian Lapuschkin, Alexander Binder, Gregoire Montavon, Klaus-Robert Mueller, Wojciech Samek
@license : BSD-2-Clause
'''

import mxnet as mx
from mxnet import nd
from .module import Module

# -------------------------------
# Max Pooling layer
# -------------------------------

class MaxPool(Module):
    def __init__(self,pool=(2,2),stride=(2,2), ctx=mx.cpu()):
        '''
        Constructor for the max pooling layer object

        Parameters
        ----------

        pool : tuple (h,w)
            the size of the pooling mask in vertical (h) and horizontal (w) direction

        stride : tuple (h,w)
            the vertical (h) and horizontal (w) step sizes between filter applications.

        ctx:    mxnet.context.Context
                device used for all mxnet.ndarray operations

        dtype:  string ('float32' | 'float64')
                dtype used for all mxnet.ndarray operations
                (mxnet default is 'float32', 'float64' supported for easier comparison with numpy)
        '''

        Module.__init__(self)

        self.pool = pool
        self.stride = stride

        self.ctx = ctx

    def forward(self,X):
        '''
        Realizes the forward pass of an input through the max pooling layer.

        Parameters
        ----------
        X : mxnet.ndarray.ndarray.NDArray
            a network input, shaped (N,H,W,D), with
            N = batch size
            H, W, D = input size in heigth, width, depth

        Returns
        -------
        Y : mxnet.ndarray.ndarray.NDArray
            the max-pooled outputs, reduced in size due to given stride and pooling size
        '''

        self.X = X
        N,H,W,D = X.shape

        hpool,   wpool   = self.pool
        hstride, wstride = self.stride

        #assume the given pooling and stride parameters are carefully chosen.
        Hout = (H - hpool) / hstride + 1
        Wout = (W - wpool) / wstride + 1

        #initialize pooled output
        self.Y = nd.zeros((N,Hout,Wout,D))

        for i in range(Hout):
            for j in range(Wout):
                self.Y[:,i,j,:] = X[:, i*hstride:i*hstride+hpool: , j*wstride:j*wstride+wpool: , : ].max(axis=(1,2))
        return self.Y


    def backward(self,DY):
        '''
        Backward-passes an input error gradient DY towards the domintly ativating neurons of this max pooling layer.

        Parameters
        ----------

        DY : mxnet.ndarray.ndarray.NDArray
            an error gradient shaped same as the output array of forward, i.e. (N,Hy,Wy,Dy) with
            N = number of samples in the batch
            Hy = heigth of the output
            Wy = width of the output
            Dy = output depth = input depth


        Returns
        -------

        DX : mxnet.ndarray.ndarray.NDArray
            the error gradient propagated towards the input

        '''

        N,H,W,D = self.X.shape

        hpool,   wpool   = self.pool
        hstride, wstride = self.stride

        #assume the given pooling and stride parameters are carefully chosen.
        Hout = (H - hpool) / hstride + 1
        Wout = (W - wpool) / wstride + 1

        #distribute the gradient towards the max activation(s)
        #the max activation value is already known via self.Y
        DX = nd.zeros_like(self.X,dtype="float")
        for i in range(Hout):
            for j in range(Wout):
                DX[:,i*hstride:i*hstride+hpool , j*wstride:j*wstride+wpool,:] += DY[:,i:i+1,j:j+1,:] * (self.Y[:,i:i+1,j:j+1,:] == self.X[:, i*hstride:i*hstride+hpool , j*wstride:j*wstride+wpool , : ])
        return DX


    def clean(self):
        self.X = None
        self.Y = None




    def _simple_lrp(self,R):
        N,H,W,D = self.X.shape

        hpool,   wpool   = self.pool
        hstride, wstride = self.stride

        #assume the given pooling and stride parameters are carefully chosen.
        Hout = (H - hpool) / hstride + 1
        Wout = (W - wpool) / wstride + 1

        Rx = nd.zeros_like(self.X,dtype="float")

        for i in range(Hout):
            for j in range(Wout):
                Z = self.Y[:,i:i+1,j:j+1,:] == self.X[:, i*hstride:i*hstride+hpool , j*wstride:j*wstride+wpool , : ]
                Zs = Z.sum(axis=(1,2),keepdims=True,dtype="float") #thanks user wodtko for reporting this bug/fix
                Rx[:,i*hstride:i*hstride+hpool , j*wstride:j*wstride+wpool,:] += (Z / Zs) * R[:,i:i+1,j:j+1,:]
        return Rx


    def _flat_lrp(self,R):
        '''
        distribute relevance for each output evenly to the output neurons' receptive fields.
        '''
        N,H,W,D = self.X.shape

        hpool,   wpool   = self.pool
        hstride, wstride = self.stride

        #assume the given pooling and stride parameters are carefully chosen.
        Hout = (H - hpool) / hstride + 1
        Wout = (W - wpool) / wstride + 1

        Rx = nd.zeros_like(self.X,dtype="float")

        for i in range(Hout):
            for j in range(Wout):
                Z = nd.ones([N,hpool,wpool,D])
                Zs = Z.sum(axis=(1,2),keepdims=True)
                Rx[:,i*hstride:i*hstride+hpool , j*wstride:j*wstride+wpool,:] += (Z / Zs) * R[:,i:i+1,j:j+1,:]
        return Rx

    def _ww_lrp(self,R):
        '''
        There are no weights to use. default to _flat_lrp(R)
        '''
        return self._flat_lrp(R)

    def _epsilon_lrp(self,R,epsilon):
        '''
        Since there is only one (or several equally strong) dominant activations, default to _simple_lrp
        '''
        return self._simple_lrp(R)

    def _alphabeta_lrp(self,R,alpha):
        '''
        Since there is only one (or several equally strong) dominant activations, default to _simple_lrp
        '''
        return self._simple_lrp(R)
