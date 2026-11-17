package br.com.prisma.financas.di

import br.com.prisma.financas.BuildConfig
import br.com.prisma.financas.core.time.Clock
import br.com.prisma.financas.data.remote.PluggyApi
import br.com.prisma.financas.data.remote.PluggyJson
import br.com.prisma.financas.data.source.PluggyTransactionSource
import br.com.prisma.financas.domain.source.TransactionSource
import dagger.Binds
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import retrofit2.Retrofit
import retrofit2.converter.kotlinx.serialization.asConverterFactory
import java.util.concurrent.TimeUnit
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
object NetworkModule {

    @Provides
    @Singleton
    fun provideClock(): Clock = Clock { System.currentTimeMillis() }

    /** Sem interceptor de log: nenhuma URL, cabeçalho ou corpo é registrado, nem em debug. */
    @Provides
    @Singleton
    fun provideOkHttp(): OkHttpClient = OkHttpClient.Builder()
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .callTimeout(60, TimeUnit.SECONDS)
        .addInterceptor { chain ->
            chain.proceed(
                chain.request().newBuilder()
                    .header("User-Agent", "PrismaFinancas/${BuildConfig.VERSION_NAME} (Android)")
                    .header("Accept", "application/json")
                    .build(),
            )
        }
        .build()

    @Provides
    @Singleton
    fun providePluggyApi(okHttp: OkHttpClient): PluggyApi = Retrofit.Builder()
        .baseUrl(PluggyApi.BASE_URL)
        .client(okHttp)
        .addConverterFactory(PluggyJson.instance.asConverterFactory("application/json".toMediaType()))
        .build()
        .create(PluggyApi::class.java)
}

@Module
@InstallIn(SingletonComponent::class)
abstract class SourceModule {
    @Binds
    abstract fun bindTransactionSource(impl: PluggyTransactionSource): TransactionSource
}
